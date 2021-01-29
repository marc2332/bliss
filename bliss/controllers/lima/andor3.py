# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .properties import LimaProperty
from .lima_base import CameraBase


class Camera(CameraBase):
    def __init__(self, name, limadev, proxy):
        super().__init__(name, limadev, proxy)
        self.name = name
        self._device = limadev
        self._proxy = proxy

    @LimaProperty
    def synchro_mode(self):
        return "IMAGE"

    @LimaProperty
    def overlap(self):
        return self._proxy.overlap

    @overlap.setter
    def overlap(self, value):
        if value is "ON":
            if self._device._proxy.acq_trigger_mode not in (
                "INTERNAL_TRIGGER",
                "EXTERNAL_TRIGGER",
            ):
                self._device._proxy.acq_trigger_mode = "INTERNAL_TRIGGER"
                self._device._proxy.prepareAcq()
        self._proxy.overlap = value
