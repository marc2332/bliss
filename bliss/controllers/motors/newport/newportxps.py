# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import time
import gevent

from bliss.common import event
from bliss import global_map
from bliss.common.axis import AxisState
from bliss.common.utils import object_method
from bliss.controllers.motor import Controller
from bliss.controllers.motors.newport.xps import XPS
from bliss.common.logtools import *

"""
Bliss controller for XPS-Q motor controller.

controller:
  class: NewportXPS
  module: newport
  name: xps-q
  description: Newport-Q test
  tcp: 160.103.146.95:5001
  nbAxes: 1
  axes:
    -
      name: omega
      group: M1
      address: 1             # first address should be 1
      velocity: 70.0
      acceleration: 320.0
      minJerkTime: 0.005
      maxJerkTime: 0.05
      steps_per_unit: 1
      backlash: 0.0
      low_limit: 0
      high_limit: 360
      offset: 0.0
      unit: deg
      autoHome: True
      user_tag: Omega
      gpio_conn: GPIO3        # GPIO connector for constant velocity pulse
      motion_hooks:
        - $newport_hook       # execute post motion
"""


class NewportXPS(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

    def move_done_event_received(self, state, axis=None):
        if state is True:
            gevent.sleep(2)

    def initialize(self):
        log_debug(self, "initialize() called")

        self.__nbAxes = self.config.get("nbAxes", int)
        comm_cfg = self.config.config_dict
        self.__xps = XPS(comm_cfg)
        global_map.register(self, children_list=[self.__xps._sock])

    def finalize(self):
        log_debug(self, "finalize() called")
        self.__sock.close()

    # Initialize each axis.
    def initialize_axis(self, axis):
        log_debug(self, "initialize_axis() called")
        axis.channel = axis.config.get("address")
        axis.group = axis.config.get("group")
        axis.autoHome = axis.config.get("autoHome")
        axis.minJerkTime = axis.config.get("minJerkTime")
        axis.maxJerkTime = axis.config.get("maxJerkTime")
        axis.gpioConn = axis.config.get("gpio_conn")

        error, reply = self.__xps.GroupInitialize(axis.group)
        if error == 0:
            log_debug(self, "NewportXPS: initialisation successful")
        elif error == -22:
            log_debug(self, "NewportXPS: Controller already initialised")
        else:
            log_error(self, "NewportXPS: Controller initialise failed: " + str(error))

        if axis.autoHome:
            self.home_search(axis, False)
        self.read_velocity(axis)

        event.connect(axis, "move_done", self.move_done_event_received)
        log_debug(self, "initialize_axis() complete")

    def finalize_axis(self):
        log_debug(self, "finalize_axis() called")

    def initialize_encoder(self, encoder):
        log_debug(self, "initialize_encoder() called")

    def read_position(self, axis):
        log_debug(self, "read_position() called")
        reply = self.__xps.GroupPositionCurrentGet(axis.group, self.__nbAxes)
        if reply[0] != 0:
            log_error(self, "NewportXPS Error: Failed to read position" + reply[1])
        else:
            return reply[int(axis.channel)]

    def read_velocity(self, axis):
        log_debug(self, "read_velocity() called")
        results = self.__xps.PositionerSGammaParametersGet(axis.group + "." + axis.name)
        if results[0] != 0:
            log_error(
                self,
                "NewportXPS Error: Unexpected response to read velocity: "
                + f"{results}",
            )
        else:
            return results[1]

    def set_velocity(self, axis, velocity):
        log_debug(self, "set_velocity() called" + str(velocity))
        error, reply = self.__xps.PositionerSGammaParametersSet(
            axis.group + "." + axis.name,
            velocity,
            axis.acceleration,
            axis.minJerkTime,
            axis.maxJerkTime,
        )
        if error != 0:
            log_error(
                self,
                f"NewportXPS Error [{error}]: Unexpected response to setting velocity: "
                + reply,
            )

    def read_acceleration(self, axis):
        log_debug(self, "read_acceleration() called")
        results = self.__xps.PositionerSGammaParametersGet(axis.group + "." + axis.name)
        if results[0] != 0:
            log_error(
                self,
                "NewportXPS Error: Unexpected response to read acceleration"
                + results[1],
            )
        else:
            return results[2]

    def set_acceleration(self, axis, acceleration):
        log_debug(self, "set_acceleration() called")
        error, reply = self.__xps.PositionerSGammaParametersSet(
            axis.group + "." + axis.name,
            axis.velocity,
            acceleration,
            axis.minJerkTime,
            axis.maxJerkTime,
        )
        if error != 0:
            log_error(
                self,
                "NewportXPS Error: Unexpected response to setting acceleration" + reply,
            )

    def start_one(self, motion):
        log_debug(self, "start_one() called")
        motor_name = motion.axis.group + "." + motion.axis.name
        error, reply = self.__xps.GroupMoveAbsolute(motor_name, [motion.target_pos])
        if error != 0:
            log_error(
                self, "NewportXPS Error: Unexpected response to move absolute" + reply
            )

    def start_all(self, *motion_list):
        log_debug(self, "start_all() called")
        if len(motion_list) == 1:
            self.start_one(motion_list[0])
        else:
            target_positions = [0, 0]
            for motion in motion_list:
                target_positions[int(motion.axis.channel) - 1] = motion.target_pos
            error, reply = self.__xps.GroupMoveAbsolute(
                motion.axis.group, target_positions
            )
            if error != 0:
                log_error(self, "NewportXPS Error: " + reply)

    def stop(self, motion):
        log_debug(self, "stop() called")
        error, reply = self.__xps.GroupMoveAbort(
            motion.axis.group + "." + motion.axis.name
        )
        if error == -22:
            log_info(self, "NewportXPS: All positioners idle")
        elif error != 0 and error != -22:
            log_error(self, "NewportXPS Error: " + reply)

    def stop_all(self, *motion_list):
        log_debug(self, "stop_all() called")
        if len(motion_list) == 1:
            self.stop(motion_list[0])
        else:
            error, reply = self.__xps.GroupMoveAbort(motion_list[0].axis.group)
            if error == -22:
                log_info(self, "NewportXPS: All positioners idle")
            elif error != 0:
                log_error(self, "NewportXPS Error: " + reply)

    def home_search(self, axis, switch):
        log_debug(self, "home_search() called")
        # Moves the motor to a repeatable starting location allows
        # homing only once after a power cycle.
        error, reply = self.__xps.GroupHomeSearch(axis.group)
        if error == 0:
            log_info(self, "NewportXPS: homing successful")
        elif error == -22:
            log_info(self, "NewportXPS: Controller already homed")
        else:
            log_error(self, "NewportXPS: Controller homing failed: " + str(error))

    def home_state(self, axis):
        log_debug(self, "home_state() called")
        return self.state(axis)

    def get_info(self, axis):
        log_debug(self, "get_info() called")
        return self.__xps.GetLibraryVersion()

    def state(self, axis):
        log_debug(self, "state() called")
        error, status = self.__xps.GroupStatusGet(axis.group)
        if error != 0:
            log_error(self, "NewportXPS Error: Failed to read status" + status)
            return AxisState("FAULT")
        if status in [
            0,  # NOTINIT state
            1,  # NOTINIT state due to an emergency brake: see positioner status
            2,  # NOTINIT state due to an emergency stop: see positioner status
            3,  # NOTINIT state due to a following error during homing
            4,  # NOTINIT state due to a following error
            5,  # NOTINIT state due to an homing timeout
            6,  # NOTINIT state due to a motion done timeout during homing
            7,  # NOTINIT state due to a KillAll command
            8,  # NOTINIT state due to an end of run after homing
            9,  # NOTINIT state due to an encoder calibration error
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
            106,  # Not initialized state due to an error with GroupKill or KillAll command
        ]:
            return AxisState(("NOTINIT", "Not Initialised"))
        if status in [
            10,  # Ready state due to an AbortMove command
            11,  # Ready state from homing
            12,  # Ready state from motion
            13,  # Ready State due to a MotionEnable command
            14,  # Ready state from slave
            15,  # Ready state from jogging
            16,  # Ready state from analog tracking
            17,  # Ready state from trajectory
            18,  # Ready state from spinning
            19,  # Ready state due to a group interlock error during motion
            56,  # Ready state from clamped
            70,  # Ready state from auto-tuning
            77,  # Ready state from excitation signal generation
            79,  # Ready state from focus
        ]:
            return AxisState("READY")
        if status in [
            20,  # Disable state
            21,  # Disabled state due to a following error on ready state
            22,  # Disabled state due to a following error during motion
            23,  # Disabled state due to a motion done timeout during moving
            24,  # Disabled state due to a following error on slave state
            25,  # Disabled state due to a following error on jogging state
            26,  # Disabled state due to a following error during trajectory
            27,  # Disabled state due to a motion done timeout during trajectory
            28,  # Disabled state due to a following error during analog tracking
            29,  # Disabled state due to a slave error during motion
            30,  # Disabled state due to a slave error on slave state
            31,  # Disabled state due to a slave error on jogging state
            32,  # Disabled state due to a slave error during trajectory
            33,  # Disabled state due to a slave error during analog tracking
            34,  # Disabled state due to a slave error on ready state
            35,  # Disabled state due to a following error on spinning state
            36,  # Disabled state due to a slave error on spinning state
            37,  # Disabled state due to a following error on auto-tuning
            38,  # Disabled state due to a slave error on auto-tuning
            39,  # Disable state due to an emergency stop on auto-tuning state
            58,  # Disabled state due to a following error during clamped
            59,  # Disabled state due to a motion done timeout during clamped
            74,  # Disable state due to a following error on excitation signal generation state
            75,  # Disable state due to a master/slave error on excitation signal generation state
            76,  # Disable state due to an emergency stop on excitation signal generation state
            80,  # Disable state due to a following error on focus state
            81,  # Disable state due to a master/slave error on focus state
            82,  # Disable state due to an emergency stop on focus state
            84,  # Disable state due to a group interlock error during moving
            85,  # Disable state due to a group interlock error during jogging
            86,  # Disable state due to a group interlock error on slave state
            87,  # Disable state due to a group interlock error during trajectory
            88,  # Disable state due to a group interlock error during analog tracking
            89,  # Disable state due to a group interlock error during spinning
            90,  # Disable state due to a group interlock error on ready state
            91,  # Disable state due to a group interlock error on auto-tuning state
            92,  # Disable state due to a group interlock error on excitation signal generation state
            93,  # Disable state due to a group interlock error on focus state
            94,  # Disabled state due to a motion done timeout during jogging
            95,  # Disabled state due to a motion done timeout during spinning
            96,  # Disabled state due to a motion done timeout during slave mode
            97,  # Disabled state due to a ZYGO error during motion
            98,  # Disabled state due to a master/slave error during trajectory
            99,  # Disable state due to a ZYGO error on jogging state
            100,  # Disabled state due to a ZYGO error during analog tracking
            101,  # Disable state due to a ZYGO error on auto-tuning state
            102,  # Disable state due to a ZYGO error on excitation signal generation state
            103,  # Disabled state due to a ZYGO error on ready state
        ]:
            return AxisState(("DISABLED", "Disabled"))
        if status in [
            43,  # Homing state
            44,  # Moving state
            45,  # Trajectory state
            46,  # Slave state due to a SlaveEnable command
            47,  # Jogging state due to a JogEnable command
            48,  # Analog tracking state due to a TrackingEnable command
            49,  # Analog interpolated encoder calibrating state
            51,  # Spinning state due to a SpinParametersSet command
            64,  # Referencing state
        ]:
            return AxisState("BUSY")
        if status in [
            40,  # Emergency braking
            41,  # Motor initialization state
            42,  # Not referenced state
            55,  # Clamped
            65,  # Clamping initialization
            68,  # Auto-tuning state
            69,  # Scaling calibration state
            73,  # Excitation signal generation state
            78,  # Focus state
            104,  # Driver initialization
            105,  # Jitter initialization
        ]:
            return AxisState("UNDECIDED", "Not categorised yet")
        return AxisState("UNKNOWN", "This should not happen")

    @object_method()
    def abort(self, axis):
        log_debug(self, "abort() called")
        error, reply = self.__xps.GroupKill(axis.group)
        if error != 0:
            log_error(self, "NewportXPS Error: abort failed" + reply)

    @object_method()
    def cv_trigger(self, axis):
        """
        Generate a pulses on the GPIO connector when the positioner reaches
        constant velocity motion.
        """
        log_debug(self, "cv_trigger start")
        motor_name = axis.group + "." + axis.name
        category = ".SGamma"
        event1 = motor_name + category + ".ConstantVelocityStart"
        action = axis.gpioConn + ".DO.DOPulse"
        error, reply = self.__xps.EventExtendedConfigurationTriggerSet(
            [event1], [0], [0], [0], [0]
        )
        if error != 0:
            log_error(self, "NewportXPS Error: " + reply)
        else:
            error, reply = self.__xps.EventExtendedConfigurationActionSet(
                [action], [4], [0], [0], [0]
            )
            if error != 0:
                log_error(self, "NewportXPS Error: " + reply)
            else:
                error, reply = self.__xps.EventExtendedStart()
                if error != 0:
                    log_error(self, "NewportXPS Error: " + reply)
                log_debug(self, "cv_trigger eventid " + str(reply))
        log_debug(self, "cv_trigger stop")
        return reply

    @object_method()
    def enable_position_compare(self, axis, start, stop, step):
        """
        Generate output pulse on the PCO connector. The first pulse is output when
        the positioner crosses the start position and the last pulse is given at the
        stop position. The difference between the start and the stop position should
        be an integer multiple of the position step.

        example: Pos.setPositionCompare(5.0, 25.0, 0.002)
                 will generate pulses between 5mm and 25mm every 0.002mm
        """
        motor_name = axis.group + "." + axis.name
        error, reply = self.__xps.PositionerPositionCompareSet(
            motor_name, start, stop, step
        )
        if error != 0:
            log_error(self, "NewportXPS Error: " + reply)
        else:
            error, reply = self.__xps.PositionerPositionCompareEnable(motor_name)
            if error != 0:
                log_error(self, "NewportXPS Error: " + reply)

    @object_method()
    def disable_position_compare(self, axis):
        """
        Disable output pulses on the PCO connector
        """
        motor_name = axis.group + "." + axis.name
        error, reply = self.__xps.PositionerPositionCompareDisable(motor_name)
        if error != 0:
            log_error(self, "NewportXPS Error: " + reply)

    @object_method()
    def event_list(self, axis):
        error, reply = self.__xps.EventExtendedAllGet()
        if error == -83:
            log_debug(self, "NewportXPS: No events in list")
        elif error != 0:
            log_error(self, "NewportXPS Error: " + reply)
        else:
            log_debug(self, "Event id list: " + reply)
            return reply

    @object_method()
    def event_remove(self, axis, id):
        error, reply = self.__xps.EventExtendedRemove(id)
