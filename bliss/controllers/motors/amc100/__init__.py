# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import gevent
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss.common.greenlet_utils import KillMask
from bliss.config.channels import Channel, Cache

from .sdk import AMC


class AMC100(Controller):
    """
    AMC100 motor controller

    configuration example:
    - class: AMC100
      host: lid15amc100
      axes:
        - name: pz
          channel: 0
          type: ECSx5050        # positioner type
          close-loop: false      # default
          target-range: 100     # is basically the window size for the closed loop (100nm)
          autopower: true       # default
          steps_per_unit: 1.
          amplitude: 25000      # 25 Volts
          velocity: 1000     # here is the frequency
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hostname = self.config.get("host")
        self._dev = AMC.Device(hostname)
        self._open_loop_move_task = dict()

    def available_positionner_types(self):
        # This method just returns the list of possible positioner type
        return self._dev.getPositionersList()

    def initialize(self):
        self.axis_settings.config_setting["acceleration"] = False
        self._dev.connect()

        self.axis_settings.persistent_setting["_set_position"] = False

    def close(self):
        self._dev.close()

    def initialize_axis(self, axis):
        channel = axis.config.get("channel", converter=int)
        axis.channel = channel

        closed_loop = axis.config.get("closed-loop", converter=bool, default=False)
        axis.closed_loop = closed_loop

        axis.settings.disable_cache("_set_position")
        axis.config.set("check_discrepancy", False)

        axis._hw_offset = Channel(f"{axis.name}:_hw_offset", default_value=0.)
        axis._target_range = Cache(axis, "target_range")

    def initialize_hardware_axis(self, axis):
        # check if axis is connected
        if not self._dev.status.getStatusConnected(axis.channel)[1]:
            raise RuntimeError(f"Axis {axis.name} is not connected to the controller")

        # set positioner Type
        positionner_type = axis.config.get("type", converter=str)
        self._dev.control.setActorParametersByName(axis.channel, positionner_type)

        # set the amplitude
        amplitude = axis.config.get("amplitude", converter=int)
        self._dev.control.setControlAmplitude(axis.channel, amplitude)

        # set the window size for the close loop if enable
        if axis.closed_loop:
            target_range = axis.config.get("target-range", converter=int, default=100)
            self._dev.control.setControlTargetRange(axis.channel, target_range)
            axis._target_range.value = target_range

        if axis.config.get("autopower", converter=bool, default=True):
            self.set_on(axis)

        # activate/deactivate the closed loop
        self._dev.control.setControlMove(axis.channel, axis.closed_loop)

        # Has the controller reset the position
        # we get get the hardware offset from
        # the last recorded position
        last_recorded_position = axis.settings.get("dial_position")
        if last_recorded_position is not None:
            axis._hw_offset.value = last_recorded_position * axis.steps_per_unit

    def set_on(self, axis):
        channel = axis.channel
        self._dev.control.setControlOutput(channel, True)

    def set_off(self, axis):
        channel = axis.channel
        self._dev.control.setControlOutput(channel, False)

    def read_position(self, axis):
        if axis.closed_loop:
            in_range = self._dev.status.getStatusTargetRange(axis.channel)[1]
            if in_range:
                hw_position = self._dev.move.getControlTargetPosition(axis.channel)[1]
                return axis._hw_offset.value + hw_position
        hw_position = self._dev.move.getPosition(axis.channel)[1]
        return axis._hw_offset.value + hw_position

    def set_position(self, axis, new_pos):
        current_pos = self._dev.move.getPosition(axis.channel)[1]
        axis._hw_offset.value = new_pos - current_pos
        return new_pos

    def read_velocity(self, axis):
        # be careful
        # the velocity here is not equivalent to
        # m/s as it a vibration frequency of the motion
        # but for now we don't have a better way to set
        # the speed.
        return self._dev.control.getControlFrequency(axis.channel)[1]

    def set_velocity(self, axis, new_velocity):
        self._dev.control.setControlFrequency(axis.channel, new_velocity)

    def state(self, axis):
        # status: string "MOVING","IN TARGET RANGE", "END OF TRAVEL",
        # "READY", "PENDING", "UNKNOWN STATE"
        open_loop_task = self._open_loop_move_task.get(axis)
        if open_loop_task:
            return AxisState("MOVING")

        status = self._dev.status.getCombinedStatus(axis.channel)[1].upper()
        if status == "MOVING":
            return AxisState("MOVING")
        elif status == "READY":
            return AxisState("READY")
        elif status == "IN TARGET RANGE":
            # as the start of movement is not synchronized
            # we need to check if the position reach the dead-band
            current_pos = self._dev.move.getPosition(axis.channel)[1]
            target_pos = self._dev.move.getControlTargetPosition(axis.channel)[1]
            target_range = axis._target_range.value
            if abs(current_pos - target_pos) > target_range:
                return AxisState("MOVING")
            else:
                return AxisState("READY")

    def start_jog(self, axis, velocity, direction):
        # if needed
        # Could use move.setControlContinousFwd or move.setControlContinousBkw
        # But those methods are only available in PRO version
        raise NotImplementedError

    def stop_jog(self, axis):
        # Could use move.setControlContinousFwd(axis.channel,False)
        # or move.setControlContinousBkw(axis.channel,False)
        raise NotImplementedError

    def limit_search(self, axis, limit):
        #
        pass

    def home_search(self, axis, switch):
        pass

    def home_state(self, axis):
        pass

    def start_one(self, motion):
        axis = motion.axis
        target_pos = motion.target_pos - axis._hw_offset.value
        if axis.closed_loop:
            self._dev.move.setControlTargetPosition(axis.channel, target_pos)
        else:
            delta = motion.delta
            backward_dir = True if delta < 0 else False
            if 0:  # PRO version
                self._dev.move.setNSteps(axis.channel, backward_dir, abs(delta))
            else:

                def move_loop():
                    ldelta = round(delta)
                    for i in range(abs(ldelta)):
                        with KillMask():
                            self._dev.move.setNSteps(axis.channel, backward_dir, 1)
                            current_pos = self._dev.move.getPosition(axis.channel)[1]
                            if ldelta >= 0:
                                if current_pos >= target_pos:
                                    break
                            else:
                                if current_pos <= target_pos:
                                    break
                        gevent.sleep(0)  # Let the hand for other request

                self._open_loop_move_task[axis] = gevent.spawn(move_loop)

    def stop(self, axis):
        if axis.closed_loop:
            curr_pos = self._dev.move.getPosition(axis.channel)[1]
            self._dev.move.setControlTargetPosition(axis.channel, curr_pos)
        else:
            if 0:  # PRO version
                self._dev.move.setControlContinousFwd(axis.channel, False)
            else:
                motion_task = self._open_loop_move_task.get(axis)
                if motion_task:
                    motion_task.kill()
