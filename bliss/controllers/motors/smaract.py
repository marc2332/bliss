# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""SmarAct motor controller

YAML_ configuration example:

.. code-block:: yaml

    plugin: emotion
    class: SmarAct
    tcp:
      url: id99smaract1
    power: Enabled                 # (1)
    axes:
      - name: rot1
        unit: degree               # (2)
        steps_per_unit: 1000000    # (2)
        velocity: 2                # (3)
        acceleration: 0            # (4)
        sensor_type: SR20          # (5)
        hold_time: 60              # (6)
        tolerance: 1e-3


1. power: initialization mode of sensors power supply (optional)
   * Disabled  : power is disabled. Almost nothing will work (disadvised)
   * Enabled   : (default) power is always on
   * PowerSave : used to avoid unnecessary heat generation (useful for
                 in-vacuum motors)
2. steps_per_unit:
   For rotary sensors, position is given in micro-degree so if you want to work
   in degrees you need to put steps_per_unit to 1.000.000.
   For linear sensors, position is given in nano-meter so if you want to work
   in milimeter you need to put steps_per_unit to 1.000.000.
3. velocity: setting to 0 disables velocity control and implicitly acceleration
   control and low vibration mode as well.
4. acceleration: setting to 0 disables acceleration control and low vibration
   mode as well.
5. sensor_type: SensorType string (optional, default is to assume the
   controller was previously configured and use its value)
6. hold_time after move/home search (optional, default is 60 meanning hold
   forever)

(Tested on ESRF-ID13: Ethernet controller with SR20 sensor)
"""

import enum
import logging
import collections

import gevent

from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from bliss.controllers.motor import Controller

# Notes:
# * After power up it reports position 0 (ie, it doesn't store its
#   position persistently (like the IcePAP does)
# * Rotary and linear positioners have different ways to get position


@enum.unique
class SensorType(enum.IntEnum):
    S = 1  # linear positioner with nano sensor
    SR = 2  # rotary positioner with nano sensor
    SP = 5  # linear positioner with nano sensor, large actuator
    SC = 6  # linear positioner with nano sensor, distance coded reference marks
    SR20 = 8  # rotary positioner with nano sensor (used on ESRF-ID13)
    M = 9  # linear positioner with micro sensor
    GD = 11  # goniometer with micro sensor (60.5mm radius)
    GE = 12  # goniometer with micro sensor (77.5mm radius)
    GF = 14  # rotary positioner with micro sensor
    G605S = 16  # goniometer with nano sensor (60.5mm radius)
    G775S = 17  # goniometer with nano sensor (77.5mm radius)
    SC500 = 18  # linear positioner with nano sensor, distance coded reference marks
    G955S = 19  # goniometer with nano sensor (95.5mm radius)
    SR77 = 20  # rotary positioner with nano sensor
    SD = 21  # like S, but with extended scanning Range
    R20ME = 22  # rotary positioner with MicroE sensor
    SR2 = 23  # like SR, for high applied masses
    SCD = 24  # like SP, but with distance coded reference marks
    SRC = 25  # like SR, but with distance coded reference marks
    SR36M = 26  # rotary positioner, no end stops
    SR36ME = 27  # rotary positioner with end stops
    SR50M = 28  # rotary positioner, no end stops
    SR50ME = 29  # rotary positioner with end stops
    G1045S = 30  # goniometer with nano sensor (104.5mm radius)
    G1395S = 31  # goniometer with nano sensor (139.5mm radius)
    MD = 32  # like M, but with large actuator
    G935M = 33  # goniometer with micro sensor (93.5mm radius)
    SHL20 = 34  # high load vertical positioner
    SCT = 35  # like SCD, but with even larger actuator


RotarySensors = SensorType.SR, SensorType.SR20, SensorType.GF, SensorType.G775S


@enum.unique
class ChannelStatus(enum.IntEnum):
    Stopped = 0  # stopped (S)
    Stepping = 1  # stepping, open-loop motion (MST)
    Scanning = 2  # scanning, (MSCA or MCSR)
    Holding = 3  # holding, target or reference pos (MPA MAA FRM)
    Targeting = 4  # targeting, closed-loop motion (MPA MAA)
    MoveDelay = 5  # move delay (power save mode)
    Calibrating = 6  # calibrating, (CS)
    FindingReferenceMark = 7  # moving to find reference mark (FRM)
    Locked = 8  # emergency stop occured (SESM)


StoppedStatuses = {ChannelStatus.Stopped, ChannelStatus.Holding, ChannelStatus.Locked}
MovingStatuses = {s for s in ChannelStatus if s not in StoppedStatuses}


@enum.unique
class SensorEnabled(enum.IntEnum):
    Disabled = 0
    Enabled = 1
    PowerSave = 2


@enum.unique
class Direction(enum.IntEnum):
    Forward = 0
    Backward = 1
    ForwardBackward = 2
    BackwardForward = 3
    ForwardAbort = 4
    BackwardAbort = 5
    ForwardBackwardAbort = 6
    BackwardForwardAbort = 7


NoHoldTime = 0
InfiniteHoldTime = 60


class SmarActError(Exception):

    ERRORS = {
        1: "Syntax Error",
        2: "Invalid Command",
        3: "Overflow",
        4: "Parse",
        5: "Too Few Parameters",
        6: "Too Many Parameters",
        7: "Invalid Parameter",
        8: "Wrong Mode",
        129: "No Sensor Present",
        140: "Sensor Disabled",
        141: "Command Overridden",
        142: "End Stop Reached",
        143: "Wrong Sensor Type",
        144: "Could Not Find Reference Mark",
        145: "Wrong End Effector Type",
        146: "Movement Locked",
        147: "Range Limit Reached",
        148: "Physical Position Unknown",
        150: "Command Not Processable",
        151: "Waiting For Trigger",
        152: "Command Not Triggerable",
        153: "Command Queue Full",
        154: "Invalid Component",
        155: "Invalid Sub Component",
        156: "Invalid Property",
        157: "Permission Denied",
    }

    def __init__(self, code, channel=-1):
        try:
            code = int(code)
            msg = self.ERRORS.setdefault(code, "Unknown error")
        except ValueError:
            msg = code
            code = -1000
        channel = int(channel)
        if channel == -1:
            msg = "Error {}: {}".format(code, msg)
        else:
            msg = "Error {} on channel {}: {}".format(code, channel, msg)
        super(SmarActError, self).__init__(msg)


def parse_reply_item(reply):
    try:
        return int(reply)
    except ValueError:
        try:
            return float(reply)
        except ValueError:
            return reply


def parse_reply(reply, cmd):
    if reply.startswith(":E"):
        channel, code = map(int, reply[2:].split(",", 1))
        if code:
            raise SmarActError(code, channel)
        return 0
    else:
        # we are in a get command for sure
        is_channel_cmd = True
        try:
            # limitation: fails if controller has more that 10 channels
            int(cmd[-1])
        except ValueError:
            is_channel_cmd = False
        if is_channel_cmd:
            reply = reply.split(",", 1)[1]
        else:
            # strip ':' + cmd name so all is left is reply
            reply = reply[len(cmd) + 1 :]
        if "," in reply:
            data = [parse_reply_item(item) for item in reply.split(",")]
        else:
            data = parse_reply_item(reply)
        return data


Features = collections.namedtuple(
    "Features", ("low_vibration_mode", "periodic_sensor_error_correction")
)


class Channel(object):

    hold_time = InfiniteHoldTime

    def __init__(self, ctrl, channel):
        self.ctrl = ctrl
        self.channel = channel
        self._sensor_type = None
        self._features = None

    def __getitem__(self, item):
        single = isinstance(item, str)
        if single:
            return self.ctrl["{}{}".format(item, self.channel)]
        else:
            return self.ctrl[["{}{}".format(i, self.channel) for i in item]]

    def __setitem__(self, item, value):
        args = [self.channel]
        if isinstance(value, (tuple, list)):
            args.extend(value)
        else:
            args.append(value)
        self.ctrl[item] = args

    def command(self, name, *args):
        return self.ctrl.command(name, self.channel, *args)

    @property
    def features(self):
        if self._features is None:
            fbin = self.ctrl["FP{},0".format(self.channel)]
            args = [bool((1 << i) & fbin) for i in range(len(Features._fields))]
            self._features = Features(*args)
        return self._features

    @property
    def sensor_type(self):
        if self._sensor_type is None:
            self._sensor_type = SensorType(self["ST"])
        return self._sensor_type

    @sensor_type.setter
    def sensor_type(self, stype):
        """Accepts SensorType, int or string"""
        if isinstance(stype, int):
            self._sensor_type = SensorType(stype)
        else:
            self._sensor_type = SensorType[stype]
        self["ST"] = int(self._sensor_type)

    @property
    def is_rotary_sensor(self):
        return self.sensor_type in RotarySensors

    @property
    def is_linear_sensor(self):
        return not self.is_rotary_sensor

    @property
    def has_low_vibration_mode(self):
        return self.features.low_vibration_mode

    @property
    def has_periodic_sensor_error_correction(self):
        return self.features.periodic_sensor_error_correction

    @property
    def closed_loop_speed(self):
        """Returns closed loop speed in micro-degree/s for rotary sensors or
        nano-meter/s for linear sensors. 0 means speed control is disabled"""
        return self["CLS"]

    @closed_loop_speed.setter
    def closed_loop_speed(self, speed):
        """Set closed loop speed

        0 disables speed control and implicitly acceleration control and
        low vibration mode as well.

        speed (int): micro-degree/s for rotary sensors or
                     nano-meter/s for linear sensors
        """
        self["CLS"] = int(speed)

    @property
    def closed_loop_acceleration(self):
        """Returns closed loop acceleration in micro-degree/s/s for rotary
        sensors or nano-meter/s/s for linear sensors. 0 means acceleration
        control is disabled"""
        return self["CLA"]

    @closed_loop_acceleration.setter
    def closed_loop_acceleration(self, acceleration):
        """Set closed loop acceleration

        0 disables acceleration control and implicitly low vibration mode
        as well.

        acceleration (int): micro-degree/s/s for rotary sensors or
                            nano-meter/s/s for linear sensors
        """
        self["CLA"] = int(acceleration)

    @property
    def is_physical_position_known(self):
        return bool(self["PPK"])

    @property
    def position(self):
        return self["A" if self.is_rotary_sensor else "P"]

    @property
    def status(self):
        return ChannelStatus(self["S"])

    @property
    def voltage_level(self):
        """Returns voltage (V)"""
        return self["VL"] / 4095.

    def set_position(self, position):
        """Set position
        position (int): micro-degree for rotary sensors or nano-meter for
                        linear sensors
        """
        self["P"] = int(position)

    def stop(self):
        self.command("S")

    def move_absolute(self, position, hold_time=None, **kwargs):
        """Start moving to the given absolute position

        pos (int): micro-degree for rotary sensors or nano-meter for linear
                   sensors
        hold_time (float): hold time. How long (s) the position is held after
                           reaching target (default: the currently configured
                           hold time. If not configured it defaults to 60
                           meaning hold forever
        revolution (int): only for rotary sensors. The absolute revolution to
                          move to (default: 0)
        """
        position = int(position)
        hold_time = min(self.hold_time if hold_time is None else hold_time, 60)
        hold_time = int(hold_time * 1000)
        if self.is_rotary_sensor:
            revolution = int(kwargs.get("revolution", 0))
            self.command("MAA", position, revolution, hold_time)
        else:
            self.command("MPA", position, hold_time)

    def find_reference_mark(self, direction, hold_time=None, auto_zero=False):
        """
        direction (Direction): search direction
        hold_time (float): hold time. How long (s) the position is held after
                           reaching target (default: the currently configured
                           hold time. If not configured it defaults to 60
                           meaning hold forever
        auto_zero (bool): if True set the position to 0 when succesfull FRM
        """
        direction = int(direction)
        auto_zero = 1 if auto_zero else 0
        hold_time = min(self.hold_time if hold_time is None else hold_time, 60)
        hold_time = int(hold_time * 1000)
        self.command("FRM", direction, hold_time, auto_zero)

    def calibrate_sensor(self):
        self.command("CS")


class SmarAct(Controller):

    DEFAULT_PORT = 5000

    def __init__(self, name, config, axes, *args, **kwargs):
        super(SmarAct, self).__init__(name, config, axes, *args, **kwargs)
        self.comm = get_comm(self.config.config_dict, port=self.DEFAULT_PORT)
        for axis_name, axis, axis_config in axes:
            axis.channel = Channel(self, axis_config.get("channel", int))
        #        self.comm._logger.setLevel('DEBUG')
        self.log = logging.getLogger(type(self).__name__)

    def __getitem__(self, item):
        single = isinstance(item, (str))
        items = (item,) if single else tuple(item)
        n = len(items)
        request = "".join([":G{}\n".format(i) for i in items])
        replies = self.comm.write_readlines(request, n)
        replies = [parse_reply(r, i) for r, i in zip(replies, items)]
        return replies[0] if single else replies

    def __setitem__(self, item, value):
        if isinstance(value, (tuple, list)):
            value = ",".join(map(str, value))
        request = ":S{}{}\n".format(item, value)
        reply = self.comm.write_readline(request)
        parse_reply(reply, item)

    def command(self, name, *args):
        value = ",".join(map(str, args))
        request = ":{}{}\n".format(name, value)
        reply = self.comm.write_readline(request)
        return parse_reply(reply, name)

    @property
    def sensor_enabled(self):
        return SensorEnabled(self["SE"])

    @sensor_enabled.setter
    def sensor_enabled(self, enabled):
        """Set sensor state

        enabled (SensorEnabled, int or string): new sensor state
        """
        if isinstance(enabled, int):
            value = SensorEnabled(enabled)
        else:
            value = SensorEnabled[enabled]
        self["SE"] = int(value)

    def initialize_hardware(self):
        # set communication mode to synchronous
        self["CM"] = 0
        self.sensor_enabled = self.config.get(
            "sensor_enabled", default=SensorEnabled.Enabled
        )

    def initialize_axis(self, axis):
        if "hold_time" in axis.config.config_dict:
            axis.channel.hold_time = axis.config.get("hold_time", float)

    def initialize_hardware_axis(self, axis):
        if "sensor_type" in axis.config.config_dict:
            new_sensor_type = SensorType[axis.config.get("sensor_type")]
            curr_sensor_type = axis.channel.sensor_type
            # writing sensor type loses the position (even if it is the same)
            # so we only write if we know it is not the correct one.
            if new_sensor_type != curr_sensor_type:
                axis.channel.sensor_type = new_sensor_type
        if not axis.channel.is_physical_position_known:
            self.log.warning(
                "%r physical position unknown (hint: do a "
                "homing to find reference mark)",
                axis.name,
            )

    def state(self, axis):
        status = axis.channel.status
        enabled = self.sensor_enabled
        if enabled == SensorEnabled.Disabled:
            states = ["OFF"]
        if status == ChannelStatus.Locked:
            states = ["OFF"]
        elif status in MovingStatuses:
            states = ["MOVING"]
        else:
            states = ["READY"]
        states.extend([status.name.upper(), enabled.name.upper()])
        return AxisState(*states)

    def stop(self, axis):
        axis.channel.stop()

    #    def stop_all(self, *motion_list):
    #        # TODO: only stop all if motion moves all existing channels
    #        self['S']

    def set_position(self, axis, pos):
        axis.channel.set_position(pos)
        return self.read_position(axis)

    def read_position(self, axis):
        if axis.channel.is_rotary_sensor:
            position, revolution = axis.channel.position
            return position
        else:
            return axis.channel.position

    def start_all(self, *motion_list):
        # TODO: figure out out to use soft. trigger to move multiple axis
        for motion in motion_list:
            self.start_one(motion)

    def start_one(self, motion):
        channel = motion.axis.channel
        channel.move_absolute(motion.target_pos)

    def calibrate(self, axis, wait=True, timeout=None):
        axis.channel.calibrate_sensor()
        if wait:
            with gevent.Timeout(timeout):
                while axis.channel.status == ChannelStatus.Calibrating:
                    gevent.sleep(0.1)
        self.sync_hard()

    def home_search(self, axis, switch):
        # counter-clockwise if positive
        direction = Direction.Backward if switch > 0 else Direction.Forward
        axis.channel.find_reference_mark(direction)

    def home_state(self, axis):
        if axis.channel.status == ChannelStatus.FindingReferenceMark:
            return AxisState("MOVING")
        else:
            return AxisState("READY")

    def read_velocity(self, axis):
        return axis.channel.closed_loop_speed

    def set_velocity(self, axis, new_velocity):
        axis.channel.closed_loop_speed = new_velocity
        return self.read_velocity(axis)

    def read_acceleration(self, axis):
        return axis.channel.closed_loop_acceleration

    def set_acceleration(self, axis, new_acceleration):
        axis.channel.closed_loop_acceleration = new_acceleration

    def set_on(self, axis):
        self.sensor_enabled = SensorEnabled.Enabled

    def set_off(self, axis):
        self.sensor_enabled = SensorEnabled.Disabled
