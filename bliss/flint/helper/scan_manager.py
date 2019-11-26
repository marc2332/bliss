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

import logging
import numpy
import functools

import gevent.event

from bliss.data.nodes.lima import ImageFormatNotSupported
from bliss.data.scan import watch_session_scans
from bliss.config.conductor.client import clean_all_redis_connection

from .data_storage import DataStorage
from bliss.flint.helper import scan_info_helper
from bliss.flint.model import flint_model
from bliss.flint.model import scan_model


_logger = logging.getLogger(__name__)


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
        self._extra_scan_info = {}

        self._last_event: Dict[
            Tuple[str, Optional[str]], Tuple[str, numpy.ndarray]
        ] = dict()

        self.__data_storage = DataStorage()
        self._end_scan_event = gevent.event.Event()
        """Event to allow to wait for the the end of a scan"""

        self._end_data_process_event = gevent.event.Event()
        """Event to allow to wait for the the end of data processing"""
        self._end_data_process_event.set()

        self.__scan: Optional[scan_model.Scan] = None
        self.__scan_id = None
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

        task.link_exception(
            functools.partial(
                self._spawn_scans_session_watch, session_name, clean_redis=True
            )
        )

        self._scans_watch_task = task

        ready_event.wait()

        return task

    def _set_absorb_events(self, absorb_events: bool):
        self.__absorb_events = absorb_events

    def __get_scan_id(self, scan_info) -> str:
        unique = scan_info.get("node_name", None)
        if unique is not None:
            return unique
        # Lets try to use the dict as unique object
        return str(id(scan_info))

    def __is_current_scan(self, scan_info) -> bool:
        unique = self.__get_scan_id(scan_info)
        return self.__scan_id == unique

    def new_scan(self, scan_info):
        unique = self.__get_scan_id(scan_info)
        if self.__scan_id is None:
            self.__scan_id = unique
        else:
            # We should receive a single new_scan per scan, but let's check anyway
            if not self.__is_current_scan(scan_info):
                _logger.debug("new_scan from %s ignored", unique)
                return

        # Initialize for further metadata
        self._extra_scan_info[unique] = {}

        self._end_scan_event.clear()
        self.__data_storage.clear()

        scan = scan_info_helper.create_scan_model(scan_info)

        channels = scan_info_helper.iter_channels(scan_info)
        for channel in channels:
            if channel.kind == "scalar":
                self.__data_storage.create_channel(channel.name, channel.master)

        plots = scan_info_helper.create_plot_model(scan_info)
        if self.__flintModel is not None:
            manager = self.__flintModel.mainManager()
            manager.updateScanAndPlots(scan, plots)
        self.__scan = scan

        scan._setState(scan_model.ScanState.PROCESSING)
        scan.scanStarted.emit()

    def new_scan_child(self, scan_info, data_channel):
        if not self.__is_current_scan(scan_info):
            unique = self.__get_scan_id(scan_info)
            _logger.debug("New scan child from %s ignored", unique)
            return
        pass

    def new_scan_data(self, data_type, master_name, data):
        scan = self.__scan
        if scan is None:
            _logger.error(
                "New scan data was received before new_scan (%s, %s)",
                data_type,
                master_name,
            )
            return
        scan_info = data["scan_info"]
        if not self.__is_current_scan(scan_info):
            unique = self.__get_scan_id(scan_info)
            _logger.debug("New scan data from %s ignored", unique)
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

    def __is_image_must_be_read(self, channel_name, image_view) -> bool:
        # FIXME: This is a trick to trig _update() function, else last_image_ready is wrong
        image_view.last_index
        redis_frame_id = image_view.last_image_ready
        if redis_frame_id == -1:
            # Mitigate with #1069
            # A signal can be emitted when there is not yet data
            # FIXME: This have to be fixed in bliss
            return False

        stored_data = self.__data_storage.get_data_else_none(channel_name)
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

    def __is_video_available(self, scan_info, image_view, channel_name) -> bool:
        """True if the video format is readable (or not yet checked) and the
        frame id have a meaning (or not yet checked)"""
        unique = self.__get_scan_id(scan_info)
        info = self._extra_scan_info[unique].get(channel_name, None)
        if info is None:
            have_meaning = image_view.is_video_frame_have_meaning()
            if have_meaning is not None:
                self._extra_scan_info[unique][channel_name] = have_meaning
                info = have_meaning
            else:
                # Default
                info = True
        return info

    def __disable_video(self, scan_info, channel_name):
        unique = self.__get_scan_id(scan_info)
        self._extra_scan_info[unique][channel_name] = False

    def __new_scan_data(self, scan_info, data_type, master_name, data):
        if data_type == "0d":
            channels_data = data["data"]
            for channel_name, channel_data in channels_data.items():
                self.__update_channel_data(channel_name, channel_data)
        elif data_type == "1d":
            raw_data = data["channel_data_node"].get(-1)
            channel_name = data["channel_name"]
            self.__update_channel_data(channel_name, raw_data)
        elif data_type == "2d":
            channel_data_node = data["channel_data_node"]
            channel_data_node.from_stream = True
            image_view = channel_data_node.get(-1)
            image_data = None
            channel_name = data["channel_name"]
            must_update = self.__is_image_must_be_read(channel_name, image_view)
            try:
                if must_update:
                    video_available = self.__is_video_available(
                        scan_info, image_view, channel_name
                    )
                    if video_available:
                        try:
                            image_data, frame_id = image_view.get_last_live_image()
                            if frame_id is None:
                                # This should never be triggered, as we should
                                # already new that frame have no meaning
                                raise RuntimeError("None frame returned")
                        except ImageFormatNotSupported:
                            _logger.debug(
                                "Error while reaching video. Reading data from the video is disabled for this scan.",
                                exc_info=True,
                            )
                            self.__disable_video(scan_info, channel_name)

                    if image_data is None:
                        image_data, frame_id = image_view.get_last_image()
            except IndexError:
                # The image could not be ready
                _logger.error("Error while reaching the last image", exc_info=True)
                image_data = None
            if image_data is not None:
                self.__update_channel_data(channel_name, image_data, frame_id=frame_id)
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

    def __update_channel_data(self, channel_name, raw_data, frame_id=None):
        scan = self.__scan
        if self.__data_storage.has_channel(channel_name):
            group_name = self.__data_storage.get_group(channel_name)
            oldSize = self.__data_storage.get_available_data_size(group_name)
            self.__data_storage.set_data(channel_name, raw_data)
            newSize = self.__data_storage.get_available_data_size(group_name)
            if newSize > oldSize:
                channels = self.__data_storage.get_channels_by_group(group_name)
                for channel_name in channels:
                    channel = scan.getChannelByName(channel_name)
                    array = self.__data_storage.get_data(channel_name)
                    # Create a view
                    array = array[0:newSize]
                    data = scan_model.Data(channel, array)
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
                data = scan_model.Data(channel, raw_data, frameId=frame_id)
                channel.setData(data)
                # FIXME: Should be fired by the Scan object (but here we have more informations)
                scan._fireScanDataUpdated(channelName=channel.name())

    def get_scan(self) -> Optional[scan_model.Scan]:
        return self.__scan

    def end_scan(self, scan_info: Dict):
        unique = self.__get_scan_id(scan_info)
        if not self.__is_current_scan(scan_info):
            _logger.debug("end_scan from %s ignored", unique)
            return

        # Clean up cache
        del self._extra_scan_info[unique]

        scan = self.__scan
        if scan is None:
            _logger.error(
                "A second end_scan (or end_scan before new_scan) from %s was received. Ignored",
                unique,
            )
            return

        try:
            assert self.__scan is not None
            self._end_scan(scan_info)
        finally:
            self.__data_storage.clear()

            scan._setState(scan_model.ScanState.FINISHED)
            scan.scanFinished.emit()

            self.__scan = None
            self.__scan_id = None
            self._end_scan_event.set()

    def _end_scan(self, scan_info: Dict):
        # Make sure all the previous data was processed
        # Cause it can be processed by another greenlet
        self._end_data_process_event.wait()

        scan = self.__scan
        updated_masters = set([])
        for group_name in self.__data_storage.groups():
            channels = self.__data_storage.get_channels_by_group(group_name)
            for channel_name in channels:
                channel = scan.getChannelByName(channel_name)
                array = self.__data_storage.get_data_else_none(channel_name)
                if array is not None:
                    data = scan_model.Data(channel, array)
                    channel.setData(data)
                updated_masters.add(group_name)

        if len(updated_masters) > 0:
            # FIXME: Should be fired by the Scan object (but here we have more informations)
            for master_name in updated_masters:
                # FIXME: This could be a single event
                scan._fireScanDataUpdated(masterDeviceName=master_name)

    def wait_end_of_scan(self):
        self._end_scan_event.wait()
