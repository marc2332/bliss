# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""\
Symetrie hexapod

YAML_ configuration example:

.. code-block:: yaml

    plugin: emotion
    class: SHexapod
    version: 2                           # (1)
    tcp:
      url: id99hexa1
    user_origin: 0 0 328.83 0 0 0        # (2)
    object_origin: 0 0 328.83 0 0 0
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

2. User/objects origins are optional, they are set at startup
"""

import gevent.lock

from collections import namedtuple
from math import pi

from bliss.comm.util import get_comm, TCP
from bliss.comm.tcp import SocketTimeout
from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller
from bliss import global_map
from bliss.common.logtools import user_print

ROLES = "tx", "ty", "tz", "rx", "ry", "rz"
Pose = namedtuple("Pose", ROLES)

# Symetrie hexapods work only with mm and deg, but mrad and microns are more useful units
CUNIT_TO_UNIT = {
    "mrad": pi / 180.0 * 1000,
    "rad": pi / 180.0,
    "micron": 1 / 1000.0,
    "mm": 1,
    "deg": 1,
}


class BaseHexapodProtocol:

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user_origin = self.config.get("user_origin", "")
        object_origin = self.config.get("object_origin", "")

        if user_origin and object_origin:
            self.set_origin(user_origin.split(), object_origin.split())

    def set_origin(self, user_origin, object_origin):
        if (len(user_origin) + len(object_origin)) != 12:
            raise ValueError(
                "Wrong parameter number: need 12 values to define user and object origin"
            )

        try:
            cmd = (
                "Q80=%f Q81=%f Q82=%f Q83=%f Q84=%f Q85=%f \
Q86=%f Q87=%f Q88=%f Q89=%f Q90=%f Q91=%f Q20=21"
                % (
                    float(user_origin[0]),
                    float(user_origin[1]),
                    float(user_origin[2]),
                    float(user_origin[3]),
                    float(user_origin[4]),
                    float(user_origin[5]),
                    float(object_origin[0]),
                    float(object_origin[1]),
                    float(object_origin[2]),
                    float(object_origin[3]),
                    float(object_origin[4]),
                    float(object_origin[5]),
                )
            )
        except ValueError:
            raise TypeError("Need float values to define user and object origin")

        self.protocol().pmac(cmd)

    def __info__(self):
        return self.get_info(None)

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
                global_map.register(
                    protocol, parents_list=[self], children_list=[protocol.comm]
                )
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

        # on this controller the homing procedure is particular so here
        # we replace the *axis.home* by the specific homing procedure.
        def _home():
            protocol = self.protocol()
            # start homing
            protocol.homing()
            # Wait the procedure to starts
            gevent.sleep(1)
            while protocol.system_status.moving:
                gevent.sleep(0.1)
            # home_done is not synchronous with moving!!!
            # Wait a little bit
            gevent.sleep(0.5)
            if not protocol.system_status.homing_done:
                user_print("Home failed check status for more info")
            # Wait that all axis are in position
            while True:
                gevent.sleep(0.2)
                if protocol.system_status.in_position:
                    break
            # Synchronize all hexapod axes.
            for axis in self.axes.values():
                axis.sync_hard()

        axis.home = _home

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
                (
                    self.__get_axis_role(axis),
                    self.__get_hw_set_position(axis) / CUNIT_TO_UNIT[axis.unit],
                )
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
                    (
                        self.__get_axis_role(motion.axis),
                        motion.target_pos / CUNIT_TO_UNIT[motion.axis.unit],
                    )
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

    def get_axis_info(self, axis):
        return self.protocol().dump()

    def read_position(self, axis):
        return CUNIT_TO_UNIT[axis.unit] * getattr(
            self.protocol().object_pose, self.__get_axis_role(axis)
        )

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

    def make_ref(self):
        self.protocol().start_homing()  # async or not?

    def reset(self):
        self.protocol().reset()


# at end of file to avoid circular import
from bliss.controllers.motors.shexapodV1 import HexapodProtocolV1  # noqa E402
from bliss.controllers.motors.shexapodV2 import HexapodProtocolV2  # noqa E402
