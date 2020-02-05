# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .properties import LimaProperty
from .lima_base import CameraBase


class Camera(CameraBase):
    def __init__(self, lima_device, name, proxy):
        CameraBase.__init__(self, name, lima_device, proxy)
        self.name = name
        self._proxy = proxy

    @LimaProperty
    def synchro_mode(self):
        return "IMAGE"

    @LimaProperty
    def pixel_rate(self):
        """
        Pco Edge/2K/4K pixel rate
        """
        return int(self._proxy.pixelRate)

    @pixel_rate.setter
    def pixel_rate(self, value):
        int_val = int(value)
        possible_pixel_rate = self.pixel_rate_valid_values

        if int_val not in possible_pixel_rate:
            raise ValueError(
                "Pixel rate on this camera "
                "can only be those values: " + ",".join(map(str, possible_pixel_rate))
            )
        else:
            self._proxy.pixelRate = int_val

    @property
    def pixel_rate_valid_values(self):
        """
        Possible pixel rate for this camera
        """
        values = self._proxy.pixelRateValidValues
        if values == "invalid":
            return [self.pixel_rate]
        else:
            return [int(x) for x in values.split(" ") if x]
