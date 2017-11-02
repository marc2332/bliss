# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import print_function
from __future__ import absolute_import

import gevent

from bliss.common import log as log
from bliss.comm.util import get_comm
from bliss.common.axis import AxisState
from bliss.common.hook import MotionHook
from bliss.common.utils import object_method
from bliss.controllers.motor import Controller

"""
Bliss controller for XPS-Q motor controller.

"""


class NewportHook(MotionHook):
    def __init__(self, name, config):
        self.config = config
        self.name = name
        super(NewportHook, self).__init__()

    def post_move(self, motion_list):
        """
        Newport motors report motion complete when in actual
        fact (for DC motors at least) there is a settling time.
        """
        gevent.sleep(0.5)


class NewportXPS(Controller):

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        log.level(10)

    def initialize(self):
        log.debug("initialize() called")
        comm_cfg = ({'tcp': {'url': self.config.get('tcp')}})
        self.__sock = get_comm(comm_cfg)
        log.info("initialize() create socket {0}".format(self.__sock))

    def finalize(self):
        log.debug("finalize() called")
        self.__sock.close()

    # Initialize each axis.
    def initialize_axis(self, axis):
        log.debug("initialize_axis() called")
        axis.channel = axis.config.get("address")
        axis.group = axis.config.get("group")
        axis.autoHome = axis.config.get("autoHome")

        command = 'GroupInitialize(' + axis.group + ')'
        error, reply = self.__sendAndReceive(command)
        if error == 0:
            log.debug("NewportXPS: initialisation successful")
        elif error == -22:
            log.debug("NewportXPS: Controller already initialised")
        else:
            log.error("NewportXPS: Controller initialise failed: ", error)

        if axis.autoHome:
            self.home_search(axis, False)

        log.debug("initialize_axis() complete")

    def finalize_axis(self):
        log.debug("finalize_axis() called")
        pass

    def initialize_encoder(self, encoder):
        log.debug("initialize_encoder() called")

    def read_position(self, axis):
        log.debug("read_position() called")
        command = 'GroupPositionCurrentGet(' + axis.group + ',double *)'
        error, reply = self.__sendAndReceive(command)
        print(reply)
        if error != 0:
            log.error("NewportXPS Error: Failed to read position", reply)
        else:
            tokens = reply.split(',')
            print(tokens[int(axis.channel)])
            print(float(tokens[int(axis.channel)]))
            return float(tokens[int(axis.channel)])

    def read_encoder(self, encoder):
        log.debug("read_encoder() called")

    def read_acceleration(self, axis):
        log.debug("read_acceleration() called")
        return 1.0

    def read_deceleration(self, axis):
        log.debug("read_deceleration() called")
        return 1.0

    def read_velocity(self, axis):
        log.debug("read_velocity() called")
        return 80.0

    def read_firstvelocity(self, axis):
        log.debug("read_firstvelocity() called")

    def set_velocity(self, axis, velocity):
        log.debug("set_velocity() called")

    def set_firstvelocity(self, axis, creep_speed):
        log.debug("set_firstvelocity() called")

    def set_acceleration(self, axis, acceleration):
        log.debug("set_acceleration() called")

    def set_deceleration(self, axis, deceleration):
        log.debug("set_deceleration() called")

    def set_position(self, axis, position):
        log.debug("set_position() called")

    def state(self, axis):
        log.debug("state() called")
        command = 'GroupStatusGet(' + axis.group + ',int *)'
        error, reply = self.__sendAndReceive(command)
        print(reply)
        if error != 0:
            log.error("NewportXPS Error: Failed to read status", reply)
            return AxisState('FAULT')
        else:
            tokens = reply.split(',')
        status = int(tokens[int(axis.channel)])
        if status in [0,   # NOTINIT state
                      1,   # NOTINIT state due to an emergency brake: see positioner status
                      2,   # NOTINIT state due to an emergency stop: see positioner status
                      3,   # NOTINIT state due to a following error during homing
                      4,   # NOTINIT state due to a following error
                      5,   # NOTINIT state due to an homing timeout
                      6,   # NOTINIT state due to a motion done timeout during homing
                      7,   # NOTINIT state due to a KillAll command
                      8,   # NOTINIT state due to an end of run after homing
                      9,   # NOTINIT state due to an encoder calibration error
                      50,  # NOTINIT state due to a mechanical zero inconsistency during homing
                      52,  # NOTINIT state due to a clamping timeout
                      60,  # NOTINIT state due to a group interlock error on not reference state
                      61,  # NOTINIT state due to a group interlock error during homing
                      63,  # NOTINIT state due to a motor initialization error
                      66,  # NOTINIT state due to a perpendicularity error homing
                      67,  # NOTINIT state due to a master/slave error during homing
                      71,  # NOTINIT state from scaling calibration
                      72,  # NOTINIT state due to a scaling calibration error
                      83,  # NOTINIT state due to a group interlock error
                      106]:  # Not initialized state due to an error with GroupKill or KillAll command
            return AxisState(("NOTINIT", "Not Initialised"))
        if status in [10,   # Ready state due to an AbortMove command
                      11,   # Ready state from homing
                      12,   # Ready state from motion
                      13,   # Ready State due to a MotionEnable command
                      14,   # Ready state from slave
                      15,   # Ready state from jogging
                      16,   # Ready state from analog tracking
                      17,   # Ready state from trajectory
                      18,   # Ready state from spinning
                      19,   # Ready state due to a group interlock error during motion
                      56,   # Ready state from clamped
                      70,   # Ready state from auto-tuning
                      77,   # Ready state from excitation signal generation
                      79]:  # Ready state from focus
            return AxisState("READY")
        if status in [20,   # Disable state
                      21,   # Disabled state due to a following error on ready state
                      22,   # Disabled state due to a following error during motion
                      23,   # Disabled state due to a motion done timeout during moving
                      24,   # Disabled state due to a following error on slave state
                      25,   # Disabled state due to a following error on jogging state
                      26,   # Disabled state due to a following error during trajectory
                      27,   # Disabled state due to a motion done timeout during trajectory
                      28,   # Disabled state due to a following error during analog tracking
                      29,   # Disabled state due to a slave error during motion
                      30,   # Disabled state due to a slave error on slave state
                      31,   # Disabled state due to a slave error on jogging state
                      32,   # Disabled state due to a slave error during trajectory
                      33,   # Disabled state due to a slave error during analog tracking
                      34,   # Disabled state due to a slave error on ready state
                      35,   # Disabled state due to a following error on spinning state
                      36,   # Disabled state due to a slave error on spinning state
                      37,   # Disabled state due to a following error on auto-tuning
                      38,   # Disabled state due to a slave error on auto-tuning
                      39,   # Disable state due to an emergency stop on auto-tuning state
                      58,   # Disabled state due to a following error during clamped
                      59,   # Disabled state due to a motion done timeout during clamped
                      74,   # Disable state due to a following error on excitation signal generation state
                      75,   # Disable state due to a master/slave error on excitation signal generation state
                      76,   # Disable state due to an emergency stop on excitation signal generation state
                      80,   # Disable state due to a following error on focus state
                      81,   # Disable state due to a master/slave error on focus state
                      82,   # Disable state due to an emergency stop on focus state
                      84,   # Disable state due to a group interlock error during moving
                      85,   # Disable state due to a group interlock error during jogging
                      86,   # Disable state due to a group interlock error on slave state
                      87,   # Disable state due to a group interlock error during trajectory
                      88,   # Disable state due to a group interlock error during analog tracking
                      89,   # Disable state due to a group interlock error during spinning
                      90,   # Disable state due to a group interlock error on ready state
                      91,   # Disable state due to a group interlock error on auto-tuning state
                      92,   # Disable state due to a group interlock error on excitation signal generation state
                      93,   # Disable state due to a group interlock error on focus state
                      94,   # Disabled state due to a motion done timeout during jogging
                      95,   # Disabled state due to a motion done timeout during spinning
                      96,   # Disabled state due to a motion done timeout during slave mode
                      97,   # Disabled state due to a ZYGO error during motion
                      98,   # Disabled state due to a master/slave error during trajectory
                      99,   # Disable state due to a ZYGO error on jogging state
                      100,  # Disabled state due to a ZYGO error during analog tracking
                      101,  # Disable state due to a ZYGO error on auto-tuning state
                      102,  # Disable state due to a ZYGO error on excitation signal generation state
                      103]:  # Disabled state due to a ZYGO error on ready state
            return AxisState(("DISABLED", "Disabled"))
        if status in [43,   # Homing state
                      44,   # Moving state
                      45,   # Trajectory state
                      46,   # Slave state due to a SlaveEnable command
                      47,   # Jogging state due to a JogEnable command
                      48,   # Analog tracking state due to a TrackingEnable command
                      49,   # Analog interpolated encoder calibrating state
                      51,   # Spinning state due to a SpinParametersSet command
                      64]:  # Referencing state
            return AxisState('BUSY')
        if status in [40,   # Emergency braking
                      41,   # Motor initialization state
                      42,   # Not referenced state
                      55,   # Clamped
                      65,   # Clamping initialization
                      68,   # Auto-tuning state
                      69,   # Scaling calibration state
                      73,   # Excitation signal generation state
                      78,   # Focus state
                      104,  # Driver initialization
                      105]:  # Jitter initialization
            return AxisState("UNDECIDED", "Not categorised yet")
        return AxisState("UNKNOWN", "This should not happen")

    def prepare_move(self, motion):
        log.debug("prepare_move() called")
        pass

    def start_one(self, motion):
        log.debug("start_one() called")
        command = 'GroupMoveAbsolute(' + motion.axis.group + ','
        command += str(motion.target_pos) + ')'
        print("Command:", command)
        error, reply = self.__sendAndReceive(command)
        print("Reply:", reply)
        if error != 0:
            log.error("NewportXPS Error: Unexpected response to move absolute", reply)

    def stop(self, motion):
        log.debug("stop() called")
        command = 'GroupMoveAbort(' + motion.axis.group + '.' + motion.axis.name + ')'
        error, reply = self.__sendAndReceive(command)
        if error != 0:
            log.error("NewportXPS Error: ", reply)

    def start_all(self, *motion_list):
        log.debug("start_all() called")

    def stop_all(self, *motion_list):
        log.debug("stop_all() called")

    def home_search(self, axis, switch):
        log.debug("home_search() called")
        # Moves the motor to a repeatable starting location allows
        # homing only once after a power cycle.
        command = 'GroupHomeSearch(' + axis.group + ')'
        error, reply = self.__sendAndReceive(command)
        if error == 0:
            log.debug("NewportXPS: homing successful")
        elif error == -22:
            log.debug("NewportXPS: Controller already homed")
        else:
            log.error("NewportXPS: Controller homing failed: ", error)

    def home_state(self, axis):
        log.debug("home_state() called")
        return self.state(axis)

    def get_info(self, axis):
        log.debug("get_info() called")

    # Send command and get return
    def __sendAndReceive(self, command):
        try:
            reply = self.__sock.write_readline(command, eol=',EndOfAPI')
            print("sock reply:", reply)
        except:
            return [-1, 'socket write_readline failed']
        else:
            pos = reply.find(',')
            return [int(reply[:pos]), reply[pos+1:]]

    @object_method()
    def abort(self, axis):
        log.debug("abort() called")
        command = 'GroupKill(' + axis.group + ')'
        error, reply = self.__sendAndReceive(command)
        if error != 0:
            log.error("NewportXPS Error: abort failed", reply)

#   Newport driver methods
