# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .lima_base import CameraBase


class Camera(CameraBase):
    def __init__(self, name, lima_device, proxy):
        CameraBase.__init__(self, name, lima_device, proxy)
        self.name = name
        self._proxy = proxy
        self._lima_device = lima_device

    def calibrate(self, expo_time):
        """
        This is a procedure and it may take time...
        return current readout time and the maximum framerate
        """
        proxy = self._lima_device.proxy
        proxy.saving_mode = "MANUAL"

        self._lima_device.prepareAcq()
        transfer_time = self._proxy.transfer_time
        readout_time = self._proxy.readout_time
        if self._proxy.image_mode == "FRAME TRANSFER":
            return transfer_time, 1 / readout_time
        else:
            return readout_time, 1 / (readout_time + transfer_time)
