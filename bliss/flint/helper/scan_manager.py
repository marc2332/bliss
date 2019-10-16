# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
""""
Manage scan events to feed with the application model
"""
from __future__ import annotations
from typing import Optional
from typing import List
from typing import Dict
from typing import Tuple

import logging
import numpy
import gevent.event

from .data_storage import DataStorage
from bliss.flint.helper import scan_info_helper
from bliss.flint.model import scan_model


_logger = logging.getLogger(__name__)


class ScanManager:
    """"Manage scan events emitted by redis.

    A new scan create a `scan_model.Scan` object. This object is registered to
    flint as a new scan. Each fearther events are propagated to this scan
    structure.
    """

    def __init__(self, flint):
        self.flint = flint
        self._refresh_task = None
        self._last_event: Dict[
            Tuple[str, Optional[str]], Tuple[str, numpy.ndarray]
        ] = dict()

        self.__data_storage = DataStorage()
        self._end_scan_event = gevent.event.Event()
        self.__scan: Optional[scan_model.Scan] = None

    def new_scan(self, scan_info):
        self._end_scan_event.clear()
        self.__data_storage.clear()

        scan = scan_info_helper.create_scan_model(scan_info)

        channels = scan_info_helper.iter_channels(scan_info)
        for channel in channels:
            if channel.kind == "scalar":
                self.__data_storage.create_channel(channel.name, channel.master)

        plots = scan_info_helper.create_plot_model(scan_info)
        manager = self.flint._manager()
        manager.updateScanAndPlots(scan, plots)
        self.__scan = scan

        scan._setState(scan_model.ScanState.PROCESSING)
        scan.scanStarted.emit()

    def new_scan_child(self, scan_info, data_channel):
        pass

    def new_scan_data(self, data_type, master_name, data):
        if data_type in ("1d", "2d"):
            key = master_name, data["channel_name"]
        else:
            key = master_name, None

        self._last_event[key] = (data_type, data)
        if self._refresh_task is None:
            self._refresh_task = gevent.spawn(self.__refresh)

    def __refresh(self):
        try:
            while self._last_event:
                local_event = self._last_event
                self._last_event = dict()
                for (master_name, _), (data_type, data) in local_event.items():
                    try:
                        self.__new_scan_data(data_type, master_name, data)
                    except Exception:
                        _logger.error("Error while reaching data", exc_info=True)
        finally:
            self._refresh_task = None

    def __new_scan_data(self, data_type, master_name, data):
        channels_data = None
        raw_data = None
        channel_name = None

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
            raw_data = image_view.get_image(-1)
            channel_name = data["channel_name"]
            self.__update_channel_data(channel_name, raw_data)
        else:
            assert False

        data_event = (
            self.flint.data_event[master_name]
            .setdefault(data_type, {})
            .setdefault(data.get("channel_index", 0), gevent.event.Event())
        )
        data_event.set()

    def __update_channel_data(self, channel_name, raw_data):
        assert self.__scan is not None
        scan = self.__scan
        if self.__data_storage.has_channel(channel_name):
            group_name = self.__data_storage.get_group(channel_name)
            oldSize = self.__data_storage.get_avaible_data_size(group_name)
            self.__data_storage.set_data(channel_name, raw_data)
            newSize = self.__data_storage.get_avaible_data_size(group_name)
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
            channel = scan.getChannelByName(channel_name)
            if channel is None:
                _logger.error("Channel '%s' not provided", channel_name)
            else:
                data = scan_model.Data(channel, raw_data)
                channel.setData(data)
                # FIXME: Should be fired by the Scan object (but here we have more informations)
                scan._fireScanDataUpdated(channelName=channel.name())

    def end_scan(self, scan_info: Dict):
        try:
            self._end_scan(scan_info)
        finally:
            self.__data_storage.clear()

            scan = self.__scan
            scan._setState(scan_model.ScanState.FINISHED)
            scan.scanFinished.emit()

            self.__scan = None
            self._end_scan_event.set()

    def _end_scan(self, scan_info: Dict):
        assert self.__scan is not None

        scan = self.__scan

        updated_masters = set([])
        for group_name in self.__data_storage.groups():
            channels = self.__data_storage.get_channels_by_group(group_name)
            for channel_name in channels:
                channel = scan.getChannelByName(channel_name)
                array = self.__data_storage.get_data(channel_name)
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
