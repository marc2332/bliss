# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Bliss controller for Mechonics CN30 controller aka PiCo 33 piezo.
# Cyril Guilloud - BCU - ESRF
# Thu 28 Jun 2018 10:39:02

# not a lot of documentation...
# see : http://wikiserv.esrf.fr/bliss/index.php/Mechonics

from bliss.common.axis import AxisState
from bliss.controllers.motor import Controller
from bliss.comm.util import get_comm, SERIAL
from bliss import global_map


class Mechonics(Controller):
    """
    Mechonics CN30 controller configuration example:

    - class: Mechonics
      serial: /dev/ttyS0
      axes:
       - name: m1
         velocity: 1
         acceleration: 1
         steps_per_unit: 1
         channel: 1
       - name: m2
         velocity: 1
         acceleration: 1
         steps_per_unit: 1
         channel: 2
       - name: m3
         velocity: 1
         acceleration: 1
         steps_per_unit: 1
         channel: 3
    """

    axes_id = {1: 0x00, 2: 0x40, 3: 0x80}
    speeds = {1: 0x30, 2: 0x20, 3: 0x10, 4: 0x00}
    directions = {"pos": 0x00, "neg": 0x08}
    steps_table = {1: 1, 2: 2, 5: 3, 10: 4, 20: 5, 50: 6, 100: 7}

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        # Communication
        comm_option = {"baudrate": 19200}
        self.serial = get_comm(self.config.config_dict, **comm_option)

        global_map.register(self, children_list=[self.serial])

        self.channels = dict()
        self.velocities = dict()
        self.positions = dict()

    def write(self, cmd):
        _cmd = cmd
        self.serial.write(_cmd)

    def read(self):
        _ans = self.serial.read()
        return _ans

    def initialize(self):
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

    def initialize_axis(self, axis):
        self.velocities[axis] = self.config.config_dict["axes"][0]["velocity"]
        self.channels[axis] = self.config.config_dict["axes"][0]["channel"]

        # re-read position saved in settings (Redis db)
        self.positions[axis] = axis.settings.get("dial_position")

    def start_one(self, motion):
        _steps_target = abs(motion.delta)

        if motion.delta < 0:
            _direction = self.directions["neg"]
        else:
            _direction = 0

        # print("motion.delta=%g  _steps_target=%d  _direction=%d" %
        #      (motion.delta, _steps_target, _direction))

        # Split movement in sub-movements.
        while _steps_target > 0:
            if _steps_target >= 100:
                _steps = 100
                _steps_code = self.steps_table[100]
            elif _steps_target >= 50:
                _steps = 50
                _steps_code = self.steps_table[50]
            elif _steps_target >= 20:
                _steps = 20
                _steps_code = self.steps_table[20]
            elif _steps_target >= 10:
                _steps = 10
                _steps_code = self.steps_table[10]
            elif _steps_target >= 5:
                _steps = 5
                _steps_code = self.steps_table[5]
            elif _steps_target >= 2:
                _steps = 2
                _steps_code = self.steps_table[2]
            else:
                _steps = 1
                _steps_code = 1

            _axis = motion.axis
            _channel = self.channels[_axis]
            _axis_id = self.axes_id[_channel]
            _velocity = _axis.velocity
            _speed_code = self.get_speed_code(_velocity)

            # print("_axis_id =%r _steps_target=%g, _speed_code =%d _direction=%d _steps_code =%d _steps=%d" %
            #       (_axis_id, _steps_target, _speed_code, _direction, _steps_code, _steps))

            _steps_target -= _steps

            _cmd = chr(_axis_id + _speed_code + _direction + _steps_code)

            self.write(_cmd)
            self.read()

        # Saves position in memory.
        self.positions[motion.axis] += motion.delta

    def state(self, axis):
        return AxisState("READY")

    def get_speed_code(self, velocity):
        if velocity >= 4:
            _speed_code = self.speeds[4]
        elif velocity >= 3:
            _speed_code = self.speeds[3]
        elif velocity >= 2:
            _speed_code = self.speeds[2]
        else:
            _speed_code = self.speeds[1]

        return _speed_code

    def read_position(self, axis):
        _pos = self.positions[axis]
        return _pos

    def set_position(self, axis, new_pos):
        self.positions[axis] = new_pos

    def read_velocity(self, axis):
        return self.velocities[axis]

    def set_velocity(self, axis, new_velocity):
        self.velocities[axis] = new_velocity
        return new_velocity
