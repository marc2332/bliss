# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import textwrap

from .roi import Roi
from .properties import LimaProperty, LimaAttrGetterSetter
from bliss.common.counter import Counter
from bliss.common.utils import autocomplete_property
from bliss.config.beacon_object import BeaconObject


class LimaImageParameters(BeaconObject):
    def __init__(self, config, proxy, name):
        self._proxy = proxy
        super().__init__(config, name=name, share_hardware=False, path=["image"])

    flip = BeaconObject.property_setting("flip", default=[False, False])

    @flip.setter
    def flip(self, value):
        assert isinstance(value, list)
        assert len(value) == 2
        assert isinstance(value[0], bool) and isinstance(value[1], bool)
        return value

    rotation = BeaconObject.property_setting("rotation", default="NONE")

    @rotation.setter
    def rotation(self, value):
        if isinstance(value, int):
            value = str(value)
        if value == "0":
            value = "NONE"
        assert isinstance(value, str)
        assert value in ["NONE", "90", "180", "270"]

        return value

    _roi = BeaconObject.property_setting("roi", default=[0, 0, 0, 0])

    @property
    def roi(self):
        return Roi(*self._roi)

    @roi.setter
    def roi(self, roi_values):
        if roi_values is None or roi_values == "NONE":
            self._roi = [0, 0, 0, 0]
        elif len(roi_values) == 4:
            self._roi = roi_values
        elif isinstance(roi_values[0], Roi):
            roi_obj = roi_values[0]
            self._roi = [roi_obj.x, roi_obj.y, roi_obj.width, roi_obj.height]
        else:
            raise TypeError(
                "Lima.image: set roi only accepts roi (class)"
                " or (x,y,width,height) values"
            )

    def to_dict(self):
        return {
            "image_rotation": self.rotation,
            "image_flip": self.flip,
            "image_roi": self._roi,
        }


class ImageCounter(Counter):
    def __init__(self, controller, proxy):
        self._proxy = proxy
        super().__init__("image", controller)

    # Standard counter interface

    # @property
    # def name(self):
    #     return "image"

    # @property
    # def _counter_controller(self):
    #     return self._controller

    # def create_acquisition_device(self, node_pars):
    #     """Instantiate the corresponding acquisition device."""
    #     return self.controller.create_master_device(node_pars)

    def __info__(self):
        # return LimaAttrGetterSetter.__info__(self)
        return textwrap.dedent(
            f"""       flip:     {self.flip}
       rotation: {self.rotation}
       roi:      {self.roi}
       binning:  {self.bin}
       height:   {self.height}
       width:    {self.width}
       type:     {self.type}"""
        )

    @property
    def dtype(self):
        # Because it is a reference
        return None

    @property
    def shape(self):
        # Because it is a reference
        return (0, 0)

    # Specific interface

    @autocomplete_property
    def proxy(self):
        return self._proxy

    @property
    def flip(self):
        return self._counter_controller._image_params.flip

    @flip.setter
    def flip(self, value):
        self._counter_controller._image_params.flip = value

    @property
    def rotation(self):
        return self._counter_controller._image_params.rotation

    @rotation.setter
    def rotation(self, value):
        self._counter_controller._image_params.rotation = value

    @property
    def roi(self):
        return self._counter_controller._image_params.roi

    @roi.setter
    def roi(self, value):
        self._counter_controller._image_params.roi = value
