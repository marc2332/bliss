# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
This module provides processing to listen scan events from Redis and to feed
with it the flint modelization relative to scans.

Here is a simplified sequence of events managed by the :class:`ScanManager`.
But events are not yet managed this way.

.. image:: _static/flint/receive-image-data.svg
    :alt: Sequence of events to deal with a Lima detector
    :align: center

The :class:`ScanManager` is then responsible to:

- Try to expose strict events of the life-cycle of the scans
- Handle data events and reach data stored in Redis or in detectors (in case of
  image data, for example)
- Send update only when data are synchronized (to avoid extra computation on
  the GUI side).
"""
from __future__ import annotations
from typing import Optional
from typing import Dict
from typing import Tuple
from typing import List

import logging
import numpy
import time

import gevent.event

from bliss.data.nodes.lima import ImageFormatNotSupported
from bliss.data.scan import watch_session_scans
from bliss.config.conductor.client import clean_all_redis_connection

from .data_storage import DataStorage
from bliss.flint.helper import scan_info_helper
from bliss.flint.model import flint_model
from bliss.flint.model import scan_model


_logger = logging.getLogger(__name__)


class _ScanCache:
    def __init__(self, scan_id: str, scan: scan_model.Scan):
        self.scan_id: str = scan_id
        """Unique id of a scan"""
        self.scan: scan_model.Scan = scan
        """Store the modelization of the scan"""
        self.video_frame_have_meaning: Dict[str, bool] = {}
        """Store metadata relative to lima video"""
        self.data_storage = DataStorage()
        """"Store 0d grouped by masters"""

    def is_video_available(self, image_view, channel_name) -> bool:
        """True if the video format is readable (or not yet checked) and the
        frame id have a meaning (or not yet checked)"""
        info = self.video_frame_have_meaning.get(channel_name, None)
        if info is None:
            have_meaning = image_view.is_video_frame_have_meaning()
            if have_meaning is not None:
                self.video_frame_have_meaning[channel_name] = have_meaning
                info = have_meaning
            else:
                # Default
                info = True
        return info

    def disable_video(self, channel_name):
        self.video_frame_have_meaning[channel_name] = False


class ScanManager:
    """"Manage scan events emitted by redis.

    A new scan create a `scan_model.Scan` object. This object is registered to
    flint as a new scan. Each further events are propagated to this scan
    structure.
    """

    def __init__(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        self._scans_watch_task = None
        self._refresh_task = None
        self.__cache: Dict[str, _ScanCache] = {}

        self._last_event: Dict[
            Tuple[str, Optional[str]], Tuple[str, numpy.ndarray]
        ] = dict()

        self._end_scan_event = gevent.event.Event()
        """Event to allow to wait for the the end of current scans"""

        self._end_data_process_event = gevent.event.Event()
        """Event to allow to wait for the the end of data processing"""

        self._end_scan_event.set()
        self._end_data_process_event.set()

        self.__absorb_events = True

        if self.__flintModel is not None:
            self.__flintModel.blissSessionChanged.connect(self.__bliss_session_changed)
            self.__bliss_session_changed()

    def __bliss_session_changed(self):
        session_name = self.__flintModel.blissSessionName()
        self._spawn_scans_session_watch(session_name)

    def _spawn_scans_session_watch(self, session_name: str, clean_redis: bool = False):
        if self._scans_watch_task:
            self._scans_watch_task.kill()
            self._scans_watch_task = None

        if clean_redis:
            # FIXME: There is maybe a problem here. As the redis connection
            # Is also stored in FlintState and is not updated
            clean_all_redis_connection()

        if session_name is None:
            return

        ready_event = gevent.event.Event()

        task = gevent.spawn(
            watch_session_scans,
            session_name,
            self.new_scan,
            self.new_scan_child,
            self.new_scan_data,
            self.end_scan,
            ready_event=ready_event,
        )

        def exception_orrured(future_exception):
            try:
                future_exception.get()
            except Exception:
                _logger.error("Error occurred in watch_session_scans", exc_info=True)
            delay = 5
            _logger.warning("Retry the Redis connect in %s seconds", delay)
            gevent.sleep(delay)
            self._spawn_scans_session_watch(session_name, clean_redis=True)

        task.link_exception(exception_orrured)
        self._scans_watch_task = task

        ready_event.wait()

        return task

    def _set_absorb_events(self, absorb_events: bool):
        self.__absorb_events = absorb_events

    def __get_scan_cache(self, scan_id) -> Optional[_ScanCache]:
        """Returns the scna cache, else None"""
        return self.__cache.get(scan_id, None)

    def __get_scan_id(self, scan_info) -> str:
        unique = scan_info.get("node_name", None)
        if unique is not None:
            return unique
        # Lets try to use the dict as unique object
        return str(id(scan_info))

    def __is_alive_scan(self, scan_info) -> bool:
        """Returns true if the scan using this scan info is still alive (still
        managed)."""
        unique = self.__get_scan_id(scan_info)
        return unique in self.__cache

    def new_scan(self, scan_info):
        unique = self.__get_scan_id(scan_info)
        if unique in self.__cache:
            # We should receive a single new_scan per scan, but let's check anyway
            _logger.debug("new_scan from %s ignored", unique)
            return

        self._end_scan_event.clear()

        # Initialize cache structure
        scan = scan_info_helper.create_scan_model(scan_info)
        cache = _ScanCache(unique, scan)

        channels = scan_info_helper.iter_channels(scan_info)
        for channel in channels:
            if channel.kind == "scalar":
                cache.data_storage.create_channel(channel.name, channel.master)

        if self.__flintModel is not None:
            self.__flintModel.addAliveScan(scan)

        self.__cache[unique] = cache

        scan._setState(scan_model.ScanState.PROCESSING)
        scan.scanStarted.emit()

    def new_scan_child(self, scan_info, data_channel):
        if not self.__is_alive_scan(scan_info):
            unique = self.__get_scan_id(scan_info)
            _logger.debug("New scan child from %s ignored", unique)
            return

    def new_scan_data(self, data_type, master_name, data):
        scan_info = data["scan_info"]
        if not self.__is_alive_scan(scan_info):
            _logger.error(
                "New scan data was received before new_scan (%s, %s)",
                data_type,
                master_name,
            )
            return

        if data_type in ("1d", "2d"):
            key = master_name, data["channel_name"]
        else:
            key = master_name, None

        self._last_event[key] = (scan_info, data_type, data)
        if self.__absorb_events:
            self._end_data_process_event.clear()
            if self._refresh_task is None:
                self._refresh_task = gevent.spawn(self.__refresh)
        else:
            self.__refresh()

    def __refresh(self):
        try:
            while self._last_event:
                local_event = self._last_event
                self._last_event = dict()
                for (
                    (master_name, _),
                    (scan_info, data_type, data),
                ) in local_event.items():
                    try:
                        self.__new_scan_data(scan_info, data_type, master_name, data)
                    except Exception:
                        _logger.error("Error while reaching data", exc_info=True)
        finally:
            self._refresh_task = None
            self._end_data_process_event.set()

    def __is_image_must_be_read(
        self, scan: scan_model.Scan, channel_name, image_view
    ) -> bool:
        # FIXME: This is a trick to trig _update() function, else last_image_ready is wrong
        image_view.last_index
        redis_frame_id = image_view.last_image_ready
        if redis_frame_id == -1:
            # Mitigate with #1069
            # A signal can be emitted when there is not yet data
            # FIXME: This have to be fixed in bliss
            return False

        stored_channel = scan.getChannelByName(channel_name)
        if stored_channel is None:
            return True

        stored_data = stored_channel.data()
        if stored_data is None:
            # Not yet data, then update is needed
            return True

        stored_frame_id = stored_data.frameId()
        if stored_frame_id is None:
            # The data is something else that an image?
            # It's weird, then update the data
            return True

        if stored_frame_id == 0:
            # Some detectors (like andor) which do not provide
            # TRIGGER_SOFT_MULTI will always returns frame_id = 0 (from video image)
            # Then if a 0 was stored it is better to update anyway
            # FIXME: This case should be managed by bliss
            return True

        # An updated is needed when bliss provides a most recent frame
        return redis_frame_id > stored_frame_id

    def __get_image(self, cache, image_view, channel_name):
        """Try to reach the image"""
        frame = None
        try:
            video_available = cache.is_video_available(image_view, channel_name)
            if video_available:
                try:
                    frame = image_view.get_last_live_image()
                    if frame.frame_number is None:
                        # This should never be triggered, as we should
                        # already new that frame have no meaning
                        raise RuntimeError("None frame returned")
                except ImageFormatNotSupported:
                    _logger.debug(
                        "Error while reaching video. Reading data from the video is disabled for this scan.",
                        exc_info=True,
                    )
                    cache.disable_video(channel_name)

            # NOTE: This comparaison can be done by the Frame object (__bool__)
            if not frame:
                # Fallback to memory buffer or file
                try:
                    frame = image_view.get_last_image()
                except Exception:
                    _logger.debug(
                        "Error while reaching image buffer/file. Reading data from the video is disabled for this scan.",
                        exc_info=True,
                    )
                    # Fallback again to the video
                    try:
                        frame = image_view.get_last_live_image()
                    except ImageFormatNotSupported:
                        pass

        except Exception:
            # The image could not be ready
            _logger.error("Error while reaching the last image", exc_info=True)
            frame = None

        # NOTE: This comparaison can be done by the Frame object (__bool__)
        if not frame:
            # Return an explicit None instead of an empty object
            return None

        return frame

    def __new_scan_data(self, scan_info, data_type, master_name, data):
        scan_id = self.__get_scan_id(scan_info)
        cache = self.__get_scan_cache(scan_id)

        if data_type == "0d":
            channels_data = data["data"]
            for channel_name, channel_data in channels_data.items():
                self.__update_channel_data(cache, channel_name, channel_data)
        elif data_type == "1d":
            raw_data = data["channel_data_node"].get(-1)
            channel_name = data["channel_name"]
            self.__update_channel_data(cache, channel_name, raw_data)
        elif data_type == "2d":
            channel_data_node = data["channel_data_node"]
            channel_data_node.from_stream = True
            image_view = channel_data_node.get(-1)
            channel_name = data["channel_name"]
            must_update = self.__is_image_must_be_read(
                cache.scan, channel_name, image_view
            )
            if must_update:
                frame = self.__get_image(cache, image_view, channel_name)
            else:
                frame = None

            if frame is not None:
                self.__update_channel_data(
                    cache,
                    channel_name,
                    raw_data=frame.data,
                    frame_id=frame.frame_number,
                    source=frame.source,
                )
        else:
            assert False

        if self.__flintModel is not None:
            flintApi = self.__flintModel.flintApi()
            data_event = (
                flintApi.data_event[master_name]
                .setdefault(data_type, {})
                .setdefault(data.get("channel_index", 0), gevent.event.Event())
            )
            data_event.set()

    def __update_channel_data(
        self, cache: _ScanCache, channel_name, raw_data, frame_id=None, source=None
    ):
        now = time.time()
        scan = cache.scan
        if cache.data_storage.has_channel(channel_name):
            group_name = cache.data_storage.get_group(channel_name)
            oldSize = cache.data_storage.get_available_data_size(group_name)
            cache.data_storage.set_data(channel_name, raw_data)
            newSize = cache.data_storage.get_available_data_size(group_name)
            if newSize > oldSize:
                channels = cache.data_storage.get_channels_by_group(group_name)
                for channel_name in channels:
                    channel = scan.getChannelByName(channel_name)
                    array = cache.data_storage.get_data(channel_name)
                    # Create a view
                    array = array[0:newSize]
                    # NOTE: No parent for the data, Python managing the life cycle of it (not Qt)
                    data = scan_model.Data(None, array, receivedTime=now)
                    channel.setData(data)

                # The group name is the master device name
                master_name = group_name
                # FIXME: Should be fired by the Scan object (but here we have more informations)
                scan._fireScanDataUpdated(masterDeviceName=master_name)
        else:
            # Everything which do not except synchronization (images and MCAs)
            channel = scan.getChannelByName(channel_name)
            if channel is None:
                _logger.error("Channel '%s' not provided", channel_name)
            else:
                # NOTE: No parent for the data, Python managing the life cycle of it (not Qt)
                data = scan_model.Data(
                    None, raw_data, frameId=frame_id, source=source, receivedTime=now
                )
                channel.setData(data)
                # FIXME: Should be fired by the Scan object (but here we have more informations)
                scan._fireScanDataUpdated(channelName=channel.name())

    def get_alive_scans(self) -> List[scan_model.Scan]:
        return [v.scan for v in self.__cache.values()]

    def end_scan(self, scan_info: Dict):
        scan_id = self.__get_scan_id(scan_info)
        if not self.__is_alive_scan(scan_info):
            _logger.debug("end_scan from %s ignored", scan_id)
            return

        cache = self.__get_scan_cache(scan_id)
        try:
            self._end_scan(cache)
        finally:
            # Clean up cache
            del self.__cache[cache.scan_id]

            scan = cache.scan
            scan._setState(scan_model.ScanState.FINISHED)
            scan.scanFinished.emit()

            if self.__flintModel is not None:
                self.__flintModel.removeAliveScan(scan)

            if len(self.__cache) == 0:
                self._end_scan_event.set()

    def _end_scan(self, cache: _ScanCache):
        # Make sure all the previous data was processed
        # Cause it can be processed by another greenlet
        self._end_data_process_event.wait()
        scan = cache.scan

        scan_type = scan.scanInfo().get("type", None)
        default_scan = scan_type in ["timescan", "loopscan"]
        push_non_aligned_data = not default_scan

        def is_same_data(array1: numpy.array, data2: scan_model.Data):
            if data2 is not None:
                array2 = data2.array()
            else:
                array2 = None
            if array1 is None and array2 is None:
                return True
            if array1 is None or array2 is None:
                return False
            return array1.shape == array2.shape

        updated_masters = set([])
        for group_name in cache.data_storage.groups():
            channels = cache.data_storage.get_channels_by_group(group_name)
            for channel_name in channels:
                channel = scan.getChannelByName(channel_name)
                array = cache.data_storage.get_data_else_none(channel_name)
                previous_data = channel.data()
                if not is_same_data(array, previous_data):
                    if push_non_aligned_data:
                        data = scan_model.Data(channel, array)
                        channel.setData(data)
                        updated_masters.add(group_name)
                    else:
                        # FIXME: THis is a hack, this should be managed in the GUI side
                        _logger.warning(
                            "Channel '%s' truncated to be able to display the data",
                            channel_name,
                        )

        if len(updated_masters) > 0:
            # FIXME: Should be fired by the Scan object (but here we have more informations)
            for master_name in updated_masters:
                # FIXME: This could be a single event
                scan._fireScanDataUpdated(masterDeviceName=master_name)

    def wait_end_of_scans(self):
        self._end_scan_event.wait()
