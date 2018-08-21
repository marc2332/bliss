# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .roi import Roi
from .properties import LimaProperty
from bliss.common.measurement import BaseCounter


class ImageCounter(BaseCounter):
    def __init__(self, controller, proxy):
        self._proxy = proxy
        self._controller = controller

    # Standard counter interface

    @property
    def name(self):
        return "image"

    @property
    def master_controller(self):
        return self._controller

    @property
    def dtype(self):
        # Because it is a reference
        return None

    @property
    def shape(self):
        # Because it is a reference
        return (0, 0)

    # Specific interface

    @property
    def proxy(self):
        return self._proxy

    @LimaProperty
    def roi(self):
        return Roi(*self._proxy.image_roi)

    @roi.setter
    def roi(self, roi_values):
        if len(roi_values) == 4:
            self._proxy.image_roi = roi_values
        elif isinstance(roi_values[0], Roi):
            roi = roi_values[0]
            self._proxy.image_roi = (roi.x, roi.y, roi.width, roi.height)
        else:
            raise TypeError(
                "Lima.image: set roi only accepts roi (class)"
                " or (x,y,width,height) values"
            )
