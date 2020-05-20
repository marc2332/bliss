# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Scan class to manage monitoring of a Lima detector
"""

from __future__ import annotations
from typing import Optional

import logging
import gevent
import datetime

from silx.gui import qt

from bliss.common import tango
from bliss.flint.model import scan_model
from bliss.data.nodes import lima

_logger = logging.getLogger(__name__)


class MonitoringScan(scan_model.Scan):

    cameraStateChanged = qt.Signal()

    def __init__(
        self,
        parent,
        channel_name: str,
        tango_address: str,
        exposure_time: Optional[float],
    ):
        scan_model.Scan.__init__(self, parent=parent)
        topMaster = scan_model.Device(self)
        topMaster.setName("monitor")
        device = scan_model.Device(self)
        device.setMaster(topMaster)
        device_name = channel_name.split(":", 1)[0]
        device.setName(device_name)
        channel = scan_model.Channel(device)
        channel.setName(channel_name)
        channel.setType(scan_model.ChannelType.IMAGE)
        self._channel = channel

        "lima_tomo_simulator:image"
        scanInfo = {
            "type": "monitoring",
            "acquisition_chain": {"mon": {"images": [channel_name]}},
            "start_time": datetime.datetime.now(),
            "count_time": exposure_time,
            "title": "Monitoring",
        }
        self.setScanInfo(scanInfo)

        self.seal()
        self.__exposure_time = exposure_time
        self.__task = None
        self.__proxy = None
        self.__tango_address = tango_address
        self.__isLive = False

    def isLive(self):
        return self.__isLive

    def __setLive(self, isLive: bool):
        if self.__isLive == isLive:
            return
        self.__isLive = isLive
        self.cameraStateChanged.emit()

    def getProxy(self):
        if self.__proxy is not None:
            return self.__proxy
        try:
            proxy = tango.DeviceProxy(self.__tango_address)
        except Exception:
            _logger.error(
                "Error while create Tango proxy to '%s'" % self.__tango_address,
                exc_info=True,
            )
            return None
        self.__proxy = proxy
        return proxy

    def __runMonitoring(self):
        while self.isMonitoring():
            proxy = self.getProxy()

            # Do not trigger the camera while the video is not enabled
            if not proxy.video_live:
                _logger.debug("Detector %s video_live not enabled", proxy)
                self.__setLive(False)
                gevent.sleep(2)
                continue
            self.__setLive(True)

            # Update the exposure time used
            if self.__exposure_time is None:
                exposure_time = float(proxy.acq_expo_time)
            else:
                exposure_time = self.__exposure_time

            # Sleep according to the user refresh rate and the exposure time
            refresh_rate = self._channel.preferedRefreshRate()
            if refresh_rate is None:
                sleep = exposure_time
            else:
                sleep = max(exposure_time, refresh_rate / 1000)
            gevent.sleep(sleep)

            _logger.debug("Polling detector %s", proxy)
            try:
                result = lima.read_video_last_image(proxy)
            except:
                _logger.error("Error while reading data", exc_info=True)
                raise
            if not self.isMonitoring():
                break
            try:
                if result is None:
                    data = scan_model.Data(
                        None,
                        array=None,
                        frameId=None,
                        source="video-mon",
                        receivedTime=datetime.datetime.now(),
                    )
                else:
                    frame, frame_number = result
                    data = scan_model.Data(
                        None,
                        array=frame,
                        frameId=frame_number,
                        source="video-mon",
                        receivedTime=datetime.datetime.now(),
                    )
                self._channel.setData(data)
                self._fireScanDataUpdated(channelName=self._channel.name())
            except:
                _logger.error("Error while propagating data", exc_info=True)
                raise
        # FIXME: It have to be joined

    def isMonitoring(self):
        return self.__task is not None

    def __exceptionOrrured(self, future_exception):
        try:
            future_exception.get()
        except Exception:
            _logger.error(
                "Error occurred while monitoring '%s'",
                self.__tango_address,
                exc_info=True,
            )
        self.__task = None
        self._setState(scan_model.ScanState.FINISHED)
        self.scanFailed.emit()
        self.scanFinished.emit()

        delay = 5
        _logger.warning("Retry the monitoring in %s seconds", delay)
        gevent.sleep(delay)
        self.startMonitoring()

    def startMonitoring(self):
        if self.__task is not None:
            raise RuntimeError("Monitoring already started")
        _logger.debug("Start monitoring")
        self._setState(scan_model.ScanState.PROCESSING)
        self.scanStarted.emit()
        task = gevent.spawn(self.__runMonitoring)
        task.link_exception(self.__exceptionOrrured)
        self.__task = task

    def stopMonitoring(self):
        if self.__task is None:
            raise RuntimeError("Monitoring already stopped")
        _logger.debug("Stop monitoring")
        task = self.__task
        self.__task = None
        task.join()
        self._setState(scan_model.ScanState.FINISHED)
        self.scanSuccessed.emit()
        self.scanFinished.emit()
