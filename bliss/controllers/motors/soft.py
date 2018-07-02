# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import inspect

import numpy

from bliss.common.axis import NoSettingsAxis, AxisState
from bliss.config.static import get_config
from bliss.controllers.motor import Controller


def get_position_func(obj, position):
    if callable(position):
        return position
    otype = type(obj)
    pos = getattr(otype, position, None)
    if pos is None or not callable(pos):
        def position_func():
            return getattr(obj, position)
    else:
        def position_func():
            return pos(obj)
    position_func.__name__ = position
    return position_func


def get_move_func(obj, move):
    if callable(move):
        return move
    otype = type(obj)
    mv = getattr(otype, move, None)
    if mv is None or not callable(mv):
        def move_func(new_mv):
            return setattr(obj, move, new_mv)
    else:
        def move_func(new_mv):
            return mv(obj, new_mv)
    move_func.__name__ = move
    return move_func


def get_stop_func(obj, stop):
    if stop is None:
        return None
    if callable(stop):
        return stop
    def stop_func():
        return getattr(obj, stop)()
    stop_func.__name__ = stop
    return stop_func


class _Config(dict):

    def to_dict(self):
        return dict(self)


class SoftController(Controller):

    def __init__(self, axis_name, obj, axis_config):
        axis_config = _Config(axis_config)
        axes = ((axis_name, NoSettingsAxis, axis_config),)
        super(SoftController, self).__init__('__soft_controller__', {},
                                             axes, (), (), ())
        self.obj = obj
        self._position = get_position_func(obj, axis_config['position'])
        self._move = get_move_func(obj, axis_config['move'])
        self._stop = get_stop_func(obj, axis_config['stop'])

    def initialize_axis(self, axis):
        pass

    def state(self, axis):
        return AxisState('READY')

    def start_one(self, motion):
        self._move(motion.target_pos)

    def start_all(self, *motion_list):
        for motion in motion_list:
            self.start_one(motion)

    def read_position(self, axis):
        return self._position()






