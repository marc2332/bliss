# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
from typing import NamedTuple
from typing import Optional
from typing import Dict
from typing import List
from typing import Any
from typing import Set
from typing import Union

import logging
import numpy
import time

import gevent.event

from bliss.data.lima_image import ImageFormatNotSupported
from bliss.data import scan as bliss_scan
from bliss.config.conductor.client import close_all_redis_connections

from .data_storage import DataStorage
from bliss.flint.helper import scan_info_helper
from bliss.flint.model import flint_model
from bliss.flint.model import scan_model
from bliss.data.nodes import lima as lima_nodes
from bliss.data.node import get_node


_logger = logging.getLogger(__name__)


class _ScalarDataEvent(NamedTuple):
    """Store scalar data event before been processing in the display pipeline

    As the data have to be processed on the fly, it is stored at another place.
    """

    scan_db_name: str
    channel_name: str


class _NdimDataEvent(NamedTuple):
    """Store an ndim data (like MCAs) data event before been processing in the
    display pipeline"""

    scan_db_name: str
    channel_name: str
    index: int
    data_bunch: List[numpy.array]


class _LimaRefDataEvent(NamedTuple):
    """Store a lima ref data event before been processing in the
    display pipeline"""

    scan_db_name: str
    channel_name: str
    dim: int
    source_node: Any
    event_data: Any


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
        self.__image_views: Dict[str, lima_nodes.LimaDataView] = {}
        """Store lima node per channel name"""
        self.__ignored_channels: Set[str] = set([])
        """Store a set of channels"""

    def ignore_channel(self, channel_name: str):
        self.__ignored_channels.add(channel_name)

    def is_ignored(self, channel_name: str):
        return channel_name in self.__ignored_channels

    def store_last_image_view(self, channel_name, image_view):
        self.__image_views[channel_name] = image_view

    def image_views(self):
        """Returns an iterator containing channel name an it's image_view"""
        return self.__image_views.items()

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


class ScanManager(bliss_scan.ScansObserver):
    """"Manage scan events emitted by redis.

    A new scan create a `scan_model.Scan` object. This object is registered to
    flint as a new scan. Each further events are propagated to this scan
    structure.
    """

    def __init__(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        self._refresh_task = None
        self.__cache: Dict[str, _ScanCache] = {}

        self._last_events: Dict[str, Union[_NdimDataEvent, _LimaRefDataEvent]] = {}
        self._last_scalar_events: Dict[str, Union[_ScalarDataEvent]] = {}

        self._end_scan_event = gevent.event.Event()
        """Event to allow to wait for the the end of current scans"""

        self._end_data_process_event = gevent.event.Event()
        """Event to allow to wait for the the end of data processing"""

        self._end_scan_event.set()
        self._end_data_process_event.set()

        self.__watcher: bliss_scan.ScansWatcher = None
        """Process following scans events from a BLISS session"""
        self.__scans_watch_task = None
        """Process following scans events from a BLISS session"""

        self.__absorb_events = True

        if self.__flintModel is not None:
            self.__flintModel.blissSessionChanged.connect(self.__bliss_session_changed)
            self.__bliss_session_changed()

    def _cache(self):
        return self.__cache

    def __bliss_session_changed(self):
        session_name = self.__flintModel.blissSessionName()
        self._spawn_scans_session_watch(session_name)

    def _spawn_scans_session_watch(self, session_name: str, clean_redis: bool = False):
        if self.__watcher is not None:
            self.__watcher.stop()
            self.__watcher = None
        if self.__scans_watch_task:
            self.__scans_watch_task.kill()
            self.__scans_watch_task = None

        if clean_redis:
            # FIXME: There is maybe a problem here. As the redis connection
            # Is also stored in FlintState and is not updated
            close_all_redis_connections()

        if session_name is None:
            return

        watcher = bliss_scan.ScansWatcher(session_name)
        watcher.set_observer(self)
        watcher.set_watch_scan_group(True)
        watcher.set_exclude_existing_scans(True)
        task = gevent.spawn(watcher.run)

        def exception_orrured(future_exception):
            try:
                future_exception.get()
            except Exception:
                _logger.error("Error occurred in ScansWatcher.run", exc_info=True)
            delay = 5
            _logger.warning("Retry the Redis connect in %s seconds", delay)
            gevent.sleep(delay)
            self._spawn_scans_session_watch(session_name, clean_redis=True)

        task.link_exception(exception_orrured)

        self.__scans_watch_task = task
        self.__watcher = watcher

    def _set_absorb_events(self, absorb_events: bool):
        self.__absorb_events = absorb_events

    def __get_scan_cache(self, scan_id) -> Optional[_ScanCache]:
        """Returns the scna cache, else None"""
        return self.__cache.get(scan_id, None)

    def __is_alive_scan(self, scan_db_name: str) -> bool:
        """Returns true if the scan using this scan info is still alive (still
        managed)."""
        return scan_db_name in self.__cache

    def on_scan_started(self, scan_db_name: str, scan_info: Dict):
        _logger.debug("on_scan_started %s", scan_db_name)
        if scan_db_name in self.__cache:
            # We should receive a single new_scan per scan, but let's check anyway
            _logger.debug("new_scan from %s ignored", scan_db_name)
            return

        if scan_db_name is not None:
            if self.__absorb_events:
                node = get_node(scan_db_name)
                is_group = node is not None and node.type == "scan_group"
            else:
                # FIXME: absorb_events is used here for testability
                # it should be done in a better way
                is_group = False
        else:
            is_group = False

        self._end_scan_event.clear()

        # Initialize cache structure
        scan = scan_info_helper.create_scan_model(scan_info, is_group)
        cache = _ScanCache(scan_db_name, scan)

        group_name = scan_info.get("group", None)
        if group_name is not None:
            group = self.__get_scan_cache(group_name)
            if group is not None:
                scan.setGroup(group.scan)
                group.scan.addSubScan(scan)

        # Initialize the storage for the channel data
        channels = scan_info_helper.iter_channels(scan_info)
        for channel_info in channels:
            if channel_info.kind == "scalar":
                group_name = None
                channel = scan.getChannelByName(channel_info.name)
                if channel is not None:
                    channel_meta = channel.metadata()
                    if channel_meta.group is not None:
                        group_name = channel_meta.group
                if group_name is None:
                    group_name = "top:" + channel_info.master
                cache.data_storage.create_channel(channel_info.name, group_name)

        if self.__flintModel is not None:
            self.__flintModel.addAliveScan(scan)

        self.__cache[scan_db_name] = cache

        scan._setState(scan_model.ScanState.PROCESSING)
        scan.scanStarted.emit()

    def on_child_created(self, scan_db_name: str, node):
        if not self.__is_alive_scan(scan_db_name):
            _logger.debug("New scan child from %s ignored", scan_db_name)
            return

    def on_scalar_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        index: int,
        data_bunch: Union[list, numpy.ndarray],
    ):
        _logger.debug("on_scalar_data_received %s %s", scan_db_name, channel_name)
        if not self.__is_alive_scan(scan_db_name):
            _logger.error(
                "New scalar data (%s) was received before the start of the scan (%s)",
                channel_name,
                scan_db_name,
            )
            return

        # The data have to be stored here on the callback event
        cache = self.__get_scan_cache(scan_db_name)
        if cache is None:
            return
        # FIXME: The index have to be used in case there is hole between 2 bunch
        # of data
        cache.data_storage.append_data(channel_name, data_bunch)

        data_event = _ScalarDataEvent(
            scan_db_name=scan_db_name, channel_name=channel_name
        )
        self.__push_scan_data(data_event)

    def on_ndim_data_received(
        self,
        scan_db_name: str,
        channel_name: str,
        dim: int,
        index: int,
        data_bunch: Union[list, numpy.ndarray],
    ):
        _logger.debug("on_ndim_data_received %s %s", scan_db_name, channel_name)
        if not self.__is_alive_scan(scan_db_name):
            _logger.error(
                "New ndim data (%s) was received before the start of the scan (%s)",
                channel_name,
                scan_db_name,
            )
            return

        data_event = _NdimDataEvent(
            scan_db_name=scan_db_name,
            channel_name=channel_name,
            index=index,
            data_bunch=data_bunch,
        )
        self.__push_scan_data(data_event)

    def on_lima_ref_received(
        self, scan_db_name: str, channel_name: str, dim: int, source_node, event_data
    ):
        _logger.debug("on_lima_ref_received %s %s", scan_db_name, channel_name)
        if not self.__is_alive_scan(scan_db_name):
            _logger.error(
                "New lima ref (%s) was received before the start of the scan (%s)",
                channel_name,
                scan_db_name,
            )
            return

        data_event = _LimaRefDataEvent(
            scan_db_name=scan_db_name,
            channel_name=channel_name,
            dim=dim,
            source_node=source_node,
            event_data=event_data,
        )
        self.__push_scan_data(data_event)

    def __push_scan_data(self, data_event):
        if isinstance(data_event, _ScalarDataEvent):
            self._last_scalar_events[data_event.channel_name] = data_event
        else:
            self._last_events[data_event.channel_name] = data_event

        if self.__absorb_events:
            self._end_data_process_event.clear()
            if self._refresh_task is None:
                self._refresh_task = gevent.spawn(self.__refresh)
        else:
            self.__refresh()

    def __refresh(self):
        try:
            while self._last_events or self._last_scalar_events:
                if self._last_scalar_events:
                    bunch_scalar_events = self._last_scalar_events
                    self._last_scalar_events = {}
                    self.__process_bunch_of_scalar_data_event(bunch_scalar_events)
                if self._last_events:
                    local_events = self._last_events
                    self._last_events = {}
                    for data_event in local_events.values():
                        try:
                            self.__process_data_event(data_event)
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

        rate = stored_channel.preferedRefreshRate()
        if rate is not None:
            now = time.time()
            # FIXME: This could be computed dinamically
            time_to_receive_data = 0.01
            next_image_time = (
                stored_data.receivedTime() + (rate / 1000.0) - time_to_receive_data
            )
            return now > next_image_time

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

    def __get_image(
        self, cache: _ScanCache, image_view: lima_nodes.LimaDataView, channel_name: str
    ):
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

    def __process_data_event(self, data_event):
        scan_db_name = data_event.scan_db_name
        cache = self.__get_scan_cache(scan_db_name)
        if cache is None:
            return

        channel_name = data_event.channel_name
        if isinstance(data_event, _ScalarDataEvent):
            # This object should go to another place
            assert False
        elif isinstance(data_event, _NdimDataEvent):
            raw_data = data_event.data_bunch[-1]
            self.__update_channel_data(cache, channel_name, raw_data)
        elif isinstance(data_event, _LimaRefDataEvent):
            channel_data_node = data_event.source_node
            channel_data_node.from_stream = True
            image_view = channel_data_node.get(-1)
            cache.store_last_image_view(channel_name, image_view)
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

    def __process_bunch_of_scalar_data_event(self, bunch_scalar_events):
        """Process scalar events and split then into groups in order to update
        the GUI in synchonized way"""

        now = time.time()
        groups = {}

        # Groups synchronized events together
        for channel_name, data_event in bunch_scalar_events.items():
            scan_db_name = data_event.scan_db_name
            cache = self.__get_scan_cache(scan_db_name)
            group_name = cache.data_storage.get_group(channel_name)
            key = scan_db_name, group_name
            if key not in groups:
                groups[key] = [channel_name]
            else:
                groups[key].append(channel_name)

        # Check for update on each groups of data
        for (scan_db_name, group_name), channel_names in groups.items():
            cache = self.__get_scan_cache(scan_db_name)
            scan = cache.scan
            updated_group_size = cache.data_storage.update_group_size(group_name)
            if updated_group_size is not None:
                channel_names = cache.data_storage.get_channels_by_group(group_name)
                channels = []
                for channel_name in channel_names:
                    channel = scan.getChannelByName(channel_name)
                    assert channel is not None

                    array = cache.data_storage.get_data(channel_name)
                    # Create a view
                    array = array[0:updated_group_size]
                    # NOTE: No parent for the data, Python managing the life cycle of it (not Qt)
                    data = scan_model.Data(None, array, receivedTime=now)
                    channel.setData(data)
                    channels.append(channel)

                # The group name can be the master device name
                if group_name.startswith("top:"):
                    master_name = group_name[4:]
                    # FIXME: Should be fired by the Scan object (but here we have more informations)
                    scan._fireScanDataUpdated(masterDeviceName=master_name)
                else:
                    # FIXME: Should be fired by the Scan object (but here we have more informations)
                    scan._fireScanDataUpdated(channels=channels)

    def __update_channel_data(
        self, cache: _ScanCache, channel_name, raw_data, frame_id=None, source=None
    ):
        now = time.time()
        scan = cache.scan

        if cache.is_ignored(channel_name):
            return

        if cache.data_storage.has_channel(channel_name):
            # This object should go to another place
            assert False
        else:
            # Everything which do not except synchronization (images and MCAs)
            channel = scan.getChannelByName(channel_name)
            if channel is None:
                cache.ignore_channel(channel_name)
                _logger.error("Channel '%s' not described in scan_info", channel_name)
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

    def on_scan_finished(self, scan_db_name: str, scan_info: Dict):
        _logger.debug("on_scan_finished %s", scan_db_name)
        if not self.__is_alive_scan(scan_db_name):
            _logger.debug("end_scan from %s ignored", scan_db_name)
            return

        cache = self.__get_scan_cache(scan_db_name)
        if cache is None:
            return
        try:
            self._end_scan(cache)
        finally:
            # Clean up cache
            del self.__cache[cache.scan_id]

            scan = cache.scan
            scan._setFinalScanInfo(scan_info)
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

        scan_info_helper.get_scan_category(scan_info=scan.scanInfo())
        scan_category = scan.type()
        # If not None, that's default scans known to have aligned data
        default_scan = scan_category is not None
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
                        # NOTE: No parent for the data, Python managing the life cycle of it (not Qt)
                        data = scan_model.Data(None, array)
                        channel.setData(data)
                        updated_masters.add(group_name)
                    else:
                        # FIXME: THis is a hack, this should be managed in the GUI side
                        _logger.warning(
                            "Channel '%s' truncated to be able to display the data",
                            channel_name,
                        )

        # Make sure the last image is displayed
        for channel_name, image_view in cache.image_views():
            frame = self.__get_image(cache, image_view, channel_name)
            # FIXME: We should only update what it was updated
            if frame is not None:
                self.__update_channel_data(
                    cache,
                    channel_name,
                    raw_data=frame.data,
                    frame_id=frame.frame_number,
                    source=frame.source,
                )

        if len(updated_masters) > 0:
            # FIXME: Should be fired by the Scan object (but here we have more informations)
            for group_name in updated_masters:
                if group_name.startswith("top:"):
                    master_name = group_name[4:]
                    scan._fireScanDataUpdated(masterDeviceName=master_name)
                else:
                    channels = []
                    channel_names = cache.data_storage.get_channels_by_group(group_name)
                    for channel_name in channel_names:
                        channel = scan.getChannelByName(channel_name)
                        channels.append(channel)
                    scan._fireScanDataUpdated(channels=channels)

    def wait_ready(self, timeout=None):
        """Wait until the scan manager is ready to follow the scan events from
        the session.

        If there is not yet a session, this does nothing.
        """
        if self.__watcher is not None:
            self.__watcher.wait_ready(timeout=timeout)

    def wait_end_of_scans(self):
        self._end_scan_event.wait()
