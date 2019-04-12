# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""\
Symetrie hexapod

YAML_ configuration example:

.. code-block:: yaml

    plugin: emotion
    class: SHexapod
    version: 2          # (1)
    tcp:
      url: id99hexa1
    axes:
      - name: h1tx
        role: tx
        unit: mm
      - name: h1ty
        role: ty
        unit: mm
      - name: h1tz
        role: tz
        unit: mm
      - name: h1rx
        role: rx
        unit: deg
      - name: h1ry
        role: ry
        unit: deg
      - name: h1rz
        role: rz
        unit: deg

1. API version: valid values: 1 or 2 (optional. If no version is given, it
   tries to discover the API version). Authors recommend to put the version
   whenever possible.
"""

import re
from collections import namedtuple

import numpy
import gevent.lock
from tabulate import tabulate

from bliss.comm.util import get_comm, TCP
from bliss.comm.tcp import SocketTimeout
from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller
from bliss.common.mapping import register
from bliss.common.logtools import LogMixin

ROLES = "tx", "ty", "tz", "rx", "ry", "rz"
Pose = namedtuple("Pose", ROLES)


class BaseHexapodProtocol(LogMixin):

    DEFAULT_PORT = None

    Pose = Pose

    def __init__(self, config):
        self.config = config
        self.eol = "\r\n"
        self.comm = get_comm(config, ctype=TCP, port=self.DEFAULT_PORT, eol=self.eol)

    #
    # To be overwritten by sub-class
    #

    def _homing(self, async_=False):
        raise NotImplementedError

    def _move(self, pose, async_=False):
        raise NotImplementedError

    def _stop(self):
        raise NotImplementedError

    def _reset(self):
        raise NotImplementedError

    #
    # API to Hexapod emotion controller
    #

    # Fist, the ones that must me overwritten sub-class

    @property
    def object_pose(self):
        """
        Return a sequence of tx, ty, tz, rx, ry, rz.
        Translation in mm; Rotation in degrees.
        """
        raise NotImplementedError

    @property
    def system_status(self):
        """
        Return object with (at least) members (bool):
        - control (true if control is active)
        - error (true if there is an error)
        - moving (true if hexapod is moving)
        """
        raise NotImplementedError

    @property
    def tspeed(self):
        """
        Returns translation speed (mm/s)
        """
        raise NotImplementedError

    @tspeed.setter
    def tspeed(self, tspeed):
        """
        Set translation speed (mm/s)
        """
        raise NotImplementedError

    @property
    def rspeed(self):
        """
        Returns rotational speed (deg/s)
        """
        raise NotImplementedError

    @rspeed.setter
    def rspeed(self, rspeed):
        """
        Set rotational speed (mm/s)
        """
        raise NotImplementedError

    @property
    def tacceleration(self):
        """
        Returns translation acceleration (mm/s)
        """
        raise NotImplementedError

    @tacceleration.setter
    def tacceleration(self, taccel):
        """
        Set translation acceleration (mm/s)
        """
        raise NotImplementedError

    @property
    def racceleration(self):
        """
        Returns rotational acceleration (deg/s)
        """
        raise NotImplementedError

    @racceleration.setter
    def racceleration(self, raccel):
        """
        Set rotational acceleration (mm/s)
        """
        raise NotImplementedError

    def start_move(self, pose):
        """
        Start absolute motion to pose (user coordinates)

        Returns:
            AsyncResult: handler which can be used to wait for the end of the
                         motion
        """
        return self._move(pose, async_=True)

    def move(self, pose):
        """
        Move to given pose (user coordinates) and wait for motion to finish
        """
        return self._move(pose)

    def start_homing(self):
        return self._homing(async_=True)

    def homing(self):
        return self._homing()

    def stop(self):
        return self._stop()

    def reset(self):
        return self._reset()


class BaseHexapodError(Exception):
    pass


class SHexapod(Controller):
    """Symetrie hexapod controller"""

    def protocol(self):
        if hasattr(self, "_protocol"):
            return self._protocol

        version = self.config.config_dict.get("version", None)
        if version == 1:
            all_klass = (HexapodProtocolV1,)
        elif version == 2:
            all_klass = (HexapodProtocolV2,)
        else:
            all_klass = (HexapodProtocolV2, HexapodProtocolV1)

        for klass in all_klass:
            try:
                protocol = klass(self.config.config_dict)
                register(protocol, parents_list=[self], children_list=[protocol.comm])
                protocol.comm.open()
                self._protocol = protocol
                break
            except gevent.socket.error:
                pass
            except SocketTimeout:
                pass
        else:
            raise ValueError("Could not find Hexapod (is it connected?)")
        return self._protocol

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

    def initialize_hardware(self):
        self.protocol().control = True

    def initialize_axis(self, axis):
        role = self.__get_axis_role(axis)
        if role not in ROLES:
            raise ValueError("Invalid role {0!r} for axis {1}".format(role, axis.name))

    def __get_axis_role(self, axis):
        return axis.config.get("role")

    def __get_hw_set_position(self, axis):
        user_set_pos = axis._set_position
        dial_set_pos = axis.user2dial(user_set_pos)
        hw_set_pos = dial_set_pos * axis.steps_per_unit
        return hw_set_pos

    def __get_hw_set_positions(self):
        return dict(
            (
                (self.__get_axis_role(axis), self.__get_hw_set_position(axis))
                for axis in self.axes.values()
            )
        )

    def start_one(self, motion):
        return self.start_all(motion)

    def start_all(self, *motion_list):
        pose_dict = dict(((r, None) for r in ROLES))
        pose_dict.update(self.__get_hw_set_positions())
        pose_dict.update(
            dict(
                (
                    (self.__get_axis_role(motion.axis), motion.target_pos)
                    for motion in motion_list
                )
            )
        )
        pose = Pose(**pose_dict)

        self.protocol().start_move(pose)

    def stop(self, axis):
        self.protocol().stop()

    def stop_all(self, *motions):
        self.protocol().stop()

    def state(self, axis):
        status = self.protocol().system_status
        state = "READY"
        if status.moving:
            state = "MOVING"
        if not status.control:
            state = "OFF"
        if status.error:
            state = "FAULT"
        state = AxisState(state)
        return state

    def get_info(self, axis):
        return self.protocol().dump()

    def read_position(self, axis):
        return getattr(self.protocol().object_pose, self.__get_axis_role(axis))

    def set_position(self, axis, new_position):
        raise NotImplementedError

    def set_on(self, axis):
        self.protocol().control = True

    def set_off(self, axis):
        self.protocol().control = False

    def read_velocity(self, axis):
        if self.__get_axis_role(axis).startswith("t"):
            return self.protocol().tspeed
        else:
            return self.protocol().rspeed

    #    def set_velocity(self, axis, new_velocity):
    #        raise NotImplementedError

    def read_acceleration(self, axis):
        if self.__get_axis_role(axis).startswith("t"):
            return self.protocol().tacceleration
        else:
            return self.protocol().racceleration


#    def set_acceleration(self, axis, new_acc):
#        raise NotImplementedError


from bliss.controllers.motors.shexapodV1 import HexapodProtocolV1
from bliss.controllers.motors.shexapodV2 import HexapodProtocolV2
