# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .roi import Roi
from .properties import LimaProperty, LimaAttrGetterSetter
from bliss.common.counter import Counter


class ImageCounter(Counter):
    def __init__(self, controller, proxy):
        self._proxy = proxy
        # self._controller = controller

        super().__init__("image", controller)

    # Standard counter interface

    # @property
    # def name(self):
    #     return "image"

    # @property
    # def controller(self):
    #     return self._controller

    # def create_acquisition_device(self, node_pars):
    #     """Instantiate the corresponding acquisition device."""
    #     return self.controller.create_master_device(node_pars)

    def __info__(self):
        return LimaAttrGetterSetter.__info__(self)

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
