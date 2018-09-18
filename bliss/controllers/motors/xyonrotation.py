# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Virtual X and Y axis which stay on top of a rotation
"""

import numpy
from bliss.controllers.motor import CalcController
from bliss.common.utils import object_method


class XYOnRotation(CalcController):
    """
    Virtual X and Y axis on top of a rotation

    Yaml sample:
        class: XYOnRotation
        #if rotation is inverted (optional default False)
        inverted: False
        #if rotation angle is in radian
        #optional default False == degree
        radian: False           # optional
        axes:
            - name: $rot
              tags: real rot
            - name: $px
              tags: real rx     # real X
            - name: $py
              tags: real ry     # real Y
            - name: sampx
              tags: x
            - name: sampy
              tags: y
    """

    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self.__inverted = False
        self.__radian = False

    def initialize(self):
        # add rotation offset in motor settings
        self.axis_settings.add("rotation_offset", float)
        CalcController.initialize(self)
        try:
            inverted = self.config.get("inverted", bool)
        except KeyError:
            self.__inverted = 1
        else:
            self.__inverted = -1 if inverted else -1

        try:
            self.__radian = self.config.get("radian", bool)
        except KeyError:
            self.__radian = False

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)

    def calc_from_real(self, real_positions):
        rx = real_positions["rx"]
        ry = real_positions["ry"]
        rot = real_positions["rot"]
        rot += self._tagged["x"][0].rotation_offset()
        if self.__radian:
            rot_rad = rot
        else:
            rot_rad = rot / 180 * numpy.pi
        rot_rad *= self.__inverted

        return {
            "x": rx * numpy.cos(rot_rad) - ry * numpy.sin(rot_rad),
            "y": rx * numpy.sin(rot_rad) + ry * numpy.cos(rot_rad),
        }

    def calc_to_real(self, positions_dict):
        x = positions_dict["x"]
        y = positions_dict["y"]
        rot_axis = self._tagged["rot"][0]
        rot = rot_axis.position()
        rot += self._tagged["x"][0].rotation_offset()
        if self.__radian:
            rot_rad = rot
        else:
            rot_rad = rot / 180 * numpy.pi
        rot_rad *= self.__inverted

        return {
            "rx": x * numpy.cos(rot_rad) + y * numpy.sin(rot_rad),
            "ry": -x * numpy.sin(rot_rad) + y * numpy.cos(rot_rad),
        }

    @object_method(types_info=("None", "float"))
    def rotation_offset(self, axis, offset=None):
        """
        get/set rotation offset between rotation motor and
        virtual axes
        """
        if offset is None:
            rotation_offset = axis.settings.get("rotation_offset")
            return rotation_offset if rotation_offset else 0
        else:
            for axis in self.axes.values():
                axis.settings.set("rotation_offset", offset)
