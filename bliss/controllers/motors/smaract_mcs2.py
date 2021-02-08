# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2021 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""SmarAct MCS2 motor controller 
   Do not confuse with the SmarAct controller which can only drive MCS model .

YAML_ configuration example:

.. code-block:: yaml

    plugin: emotion
    class: SmarAct_MCS2
    name: beutier_polariser
    tcp:
      url: smaractid016
    axes:
      - name: rot1
        channel: 0                 # (1)
        unit: mm               
        steps_per_unit: 1e9        # (2)
        velocity: 2                # (3)
        acceleration: 0            # (4)
        positioner_type: SL_S1SS   # (5)
        hold_time: -1              # (6)
        power_mode: Enabled        # (7)
        tolerance: 1e-3

1. channel: the channel number of the positioner, starts from 0
2. steps_per_unit:
   For linear positioner the resolution is 1 pico-meter (1e-12). If set to 1e9 
   the position will be in millimeter.
   For rotary positioner the resolution is 1 nano-degree (1e-9). If set to 1e9 
   the position will be in degree.
3. velocity: setting to 0 disables velocity control and implicitly acceleration
   control and low vibration mode as well.
4. acceleration: setting to 0 disables acceleration control and low vibration
   mode as well.
5. positioner_type: PositionerType string (optional, default is to assume the
   controller was previously configured and use its value).
   Warning: do not change this parameter if you are not sure, it can damage the 
   positioner.
6. hold_time: This property specifies how long (in ms) the position is actively
   held after reaching the target position. After the hold time elapsed the 
   channel is stopped and the control-loop is disabled.
   A value of 0 deactivates this feature, a value of -1 sets the channel to infinite holding.
7. power: initialization mode of the positioner power supply (optional)
   * Disabled  : the positioner power supply is turned off continuously.
   * Enabled   : (default) the positioner is continuously supplied with power.
   * PowerSave : the positioner power supply is pulsed to keep the heat generation low. (useful for
                 in-vacuum motors)

(Tested on ESRF-ID10: Ethernet controller with SL_S1SS (Linear) and  SR_S1S5S (small rotary) positioners)
"""

import enum
import collections

import gevent

from bliss.common.axis import AxisState
from bliss.comm.util import get_comm
from bliss.controllers.motor import Controller
from bliss.common.logtools import log_debug, log_warning
from bliss import global_map

# Notes:
# * After power up it reports position 0 (ie, it doesn't store its
#   position persistently (like the IcePAP does)
# * Rotary and linear positioners have different ways to get position


@enum.unique
class PositionerType(enum.IntEnum):
    SL_S1SS = 300  # linear positioner former S fo MCS1
    SR_S1S5S = 309  # small rotary positioner, former SR20 for MCS1


RotaryPositioners = (PositionerType.SR_S1S5S,)


@enum.unique
class PowerMode(enum.IntEnum):
    Disabled = 0
    Enabled = 1
    PowerSave = 2


NoHoldTime = 0
InfiniteHoldTime = -1


class SmarActMCS2Status(object):
    """ Utility class to decode axis, module, device or 
        reference option status.        
        Bit value can be read/write using attribute name
        corresponding to the bit-definition names.
        Attributes are of type boolean.
    """

    def __init__(self, value, bitdef):
        self._valdict = dict([(name, False) for name, bitidx in bitdef])
        self._bitdef = bitdef
        self.set(value)

    def set(self, value):
        self._value = value
        for name, bitidx in self._bitdef:
            self._valdict[name] = bool(value & (1 << bitidx))
            self.__dict__[name] = self._valdict[name]

    def get(self):
        val = 0
        for name, bitidx in self._bitdef:
            val += self.__dict__[name] << bitidx
        return val

    def __info__(self):
        return self.__str__()

    def __str__(self):
        stastr = ""
        for name, bitidx in self._bitdef:
            stastr += " * %20.20s = %s\n" % (name, self.__dict__[name])
        return stastr


DEVICE_STATUS_BITS = (
    ("HM_PRESENT", 0),
    ("MOVEMENT_LOCKED", 1),
    ("AMPLIFIER_LOCKED", 2),
    ("INTERNAL_COMM_FAILURE", 8),
    ("IS_STREAMING", 12),
)

MODULE_STATUS_BITS = (
    ("SM_PRESENT", 0),
    ("BOOSTER_PRESENT", 1),
    ("ADJUSTEMENT_PRESET", 2),
    ("IOM_PRESET", 3),
    ("INTERNAL_COMM_FAILURE", 8),
    ("FAN_FAILURE", 11),
    ("POWER_SUPPLY_FAILURE", 12),
    ("POWER_SUPPLY_OVERLOAD", 13),
    ("OVER_TEMPERATURE", 14),
)
CHANNEL_STATUS_BITS = (
    ("ACTIVELY_MOVING", 0),
    ("CLOSED_LOOP_ACTIVE", 1),
    ("CALIBRATING", 2),
    ("REFERENCING", 3),
    ("MOVE_DELAYED", 4),
    ("SENSOR_PRESENT", 5),
    ("IS_CALIBRATED", 6),
    ("IS_REFERENCED", 7),
    ("END_STOP_REACHED", 8),
    ("RANGE_LIMIT_REACHED", 9),
    ("FOLLOWING_LIMIT_REACHED", 10),
    ("MOVEMENT_FAILED", 11),
    ("IS_STREAMING", 12),
    ("POSITIONER_OVERLOAD", 13),
    ("OVER_TEMPERATURE", 14),
    ("REFERENCE_MARK", 15),
    ("IS_PHASED", 16),
    ("POSITIONER_FAULT", 17),
    ("AMPLIFIER_ENABLED", 18),
    ("IN_POSITION", 19),
)

CHANNEL_REF_OPTION_BITS = (
    ("START_DIR", 0),
    ("REVERSE_DIR", 1),
    ("AUTO_ZERO", 2),
    ("ABORT_ON_ENDSTOP", 3),
    ("CONTINUE_ON_REF_FOUND", 4),
    ("STOP_ON_REF_FOUND", 5),
)


class SmarActMCS2Error(Exception):
    def __init__(self, error, channel=None):
        err = error.split(",")
        code = int(err[0])
        msg = err[1].strip()
        if channel == None:
            msg = "Error {}: {}".format(code, msg)
        else:
            msg = "Error {} on channel {}: {}".format(code, channel, msg)
        super().__init__(msg)


class Channel:

    hold_time = InfiniteHoldTime

    def __init__(self, ctrl, channel):
        self.ctrl = ctrl
        self.channel = channel
        self._positioner_type = None

    def get_property(self, prop):
        cmd = f"{prop}?"
        return self.ctrl.write_read(cmd, self.channel)

    def set_property(self, prop, value):
        cmd = f"{prop} {value}"
        self.ctrl.write(cmd, self.channel)

    def command(self, cmd):
        """ a command do not need a channel number
        """
        self.ctrl.write(cmd)

    @property
    def positioner_type(self):
        if self._positioner_type is None:
            self._positioner_type = PositionerType(int(self.get_property(":PTYPE")))
        return self._positioner_type

    @positioner_type.setter
    def positioner_type(self, ptype):
        """Accepts PositionerType, int or string"""
        if isinstance(ptype, int):
            self._positioner_type = PositionerType(ptype)
        else:
            self._positioner_type = PositionerType[ptype]
        self.set_property(":PTYPE", int(self._positioner_type))

    @property
    def is_rotary_sensor(self):
        return self.positioner_type in RotaryPositioners

    @property
    def is_linear_sensor(self):
        return not self.is_rotary_sensor

    @property
    def closed_loop_speed(self):
        """Returns closed loop speed in nano-degree/s for rotary sensors or
        pico-meter/s for linear sensors. 0 means speed control is disabled"""
        return int(self.get_property(":VEL"))

    @closed_loop_speed.setter
    def closed_loop_speed(self, speed):
        """Set closed loop speed

        0 disables speed control and implicitly acceleration control and
        low vibration mode as well.

        speed (int): nano-degree/s for rotary sensors or
                     pico-meter/s for linear sensors
        """
        self.set_property(":VEL", int(speed))

    @property
    def closed_loop_acceleration(self):
        """Returns closed loop acceleration in nano-degree/s/s for rotary
        sensors or pico-meter/s/s for linear sensors. 0 means acceleration
        control is disabled"""
        return int(self.get_property(":ACC"))

    @closed_loop_acceleration.setter
    def closed_loop_acceleration(self, acceleration):
        """Set closed loop acceleration

        0 disables acceleration control and implicitly low vibration mode
        as well.

        acceleration (int): nano-degree/s/s for rotary sensors or
                            pico-meter/s/s for linear sensors
        """
        self.set_property(":ACC", int(acceleration))

    @property
    def is_physical_position_known(self):
        status = self.status
        return status.IS_REFERENCED

    @property
    def position(self):
        return int(self.get_property(":POS"))

    @property
    def hold_time(self):
        return int(self.get_property(":HOLD"))

    @hold_time.setter
    def hold_time(self, time):
        self.set_property(":HOLD", int(time))

    def set_position(self, position):
        """Set position
        position (int): nano-degree for rotary sensors or pico-meter for
                        linear sensors
        """
        self.get_property(":POS", int(position))

    def stop(self):
        self.command(f":STOP{self.channel}")

    def move_absolute(self, position):
        """Start moving to the given absolute position

        pos (int): micro-degree for rotary sensors or nano-meter for linear
                   sensors
        """
        position = int(position)
        self.command(f":MOVE{self.channel} {position}")

    def find_reference_mark(self, direction, auto_zero=False):
        """
        direction (Direction): search direction
        auto_zero (bool): if True set the position to 0 when succesfull

        The behavior of the positioner while referencing depends of the
        following independent options. A bit-wise property (CHAN#:REF:OPT) 
        provides r/w access to these options:
        Start Direction:  Defines the direction in which the posi-
                           tioner will start to look for a reference. The
                           movement starts in backward direction if
                           this flag is set.
        Reverse Direction: Only relevant for positioners that have
                           multiple reference marks. Will reverse the
                           search direction as soon as the first refer-
                           ence mark is found.
        Auto Zero:         The current position is set to zero upon
                           finding the reference position.
        Abort On End Stop: Will abort the referencing on the first end
                           stop that is encountered.
        Continue On Reference Found: Will not stop the movement of the posi-
                           tioner once the reference is found. The po-
                           sitioner must be stopped manually.
        Stop On Reference Found: Will stop the movement of the positioner
                           immediately after finding the reference.
        """
        ref_opt_status = self.read_reference_option_status()

        log_debug(self, f"before changing ref_options: \n{ref_opt_status}")

        direction = int(direction)
        direction = False if direction == 1 else True

        ref_opt_status.START_DIR = direction
        ref_opt_status.AUTO_ZERO = auto_zero

        # now apply new reference search options
        refopt = ref_opt_status.get()
        self.set_property(":REF:OPT", refopt)
        log_debug(self, f"new ref_options: \n{ref_opt_status}")

        self.command(f":REF{self.channel}")

    def read_reference_option_status(self):
        ref_opt = int(self.get_property(":REF:OPT"))
        ref_opt_status = SmarActMCS2Status(ref_opt, CHANNEL_REF_OPTION_BITS)
        return ref_opt_status

    def calibrate(self, wait=True, timeout=None):
        """ Start a new calibration of the positioner
        Be careful when using this command that the positioner has enough
        freedom to move without damaging other equipment.
        """
        # TODO: creat a bit-status to get/set calibration options, :CAL:OPT
        #

        self.command(f":CAL{self.channel}")
        if wait:
            with gevent.Timeout(timeout):
                while axis.channel.status.CALIBRATING:
                    gevent.sleep(0.1)
        self.ctrl.sync_hard()

    @property
    def power_mode(self):
        return PowerMode(int(self.get_property(":SENS:MODE")))

    @power_mode.setter
    def power_mode(self, mode):
        """Set power mode

        mode (PowerMode int or string): new power mode
        """
        if isinstance(mode, int):
            value = PowerMode(mode)
        else:
            value = PowerMode[mode]
        self.set_property(":SENS:MODE", int(value))

    @property
    def status(self):
        chan_status, _, _ = self.ctrl.read_status(self.channel)
        return chan_status

    @property
    def info_status(self):
        self.ctrl.info_status(self.channel)


class SmarAct_MCS2(Controller):

    DEFAULT_PORT = 55551

    def _flush_errors(self):
        request = ":SYST:ERR:COUN?\n"
        cnt = int(self._comm.write_readline(request.encode()))
        for i in range(cnt):
            request = ":SYST:ERR?\n"
            err = self._comm.write_readline(request.encode())

    def _check_error(self, channel=None):
        request = ":SYST:ERR:COUN?\n"
        cnt = self._comm.write_readline(request.encode())
        if int(cnt) != 0:
            request = ":SYST:ERR?\n"
            err = self._comm.write_readline(request.encode()).decode()
            raise SmarActMCS2Error(err, channel)

    def write(self, cmd, channel=None):
        chan = f":CHAN{channel}" if channel != None else ""
        request = f"{chan}{cmd}\n"
        log_debug(self, f"request = {request}")
        self._comm.write(request.encode())
        self._check_error(channel)

    def write_read(self, cmd, channel=None):
        chan = f":CHAN{channel}" if channel != None else ""
        request = f"{chan}{cmd}\n"
        log_debug(self, f"request = {request}")
        reply = self._comm.write_readline(request.encode())
        self._check_error(channel)
        reply = reply.decode()
        return reply

    def initialize(self):
        self._smaract_state = AxisState()
        # SmarAct positioners do not require any physical limit switches to
        # detect the end of the travel range while moving. The MCS2 features
        # a software-driven endstop detection. If a mechanical blockage
        # is detected while performing a closed-loop movement the channel is stopped.
        # We add here a new state since no limit-switch exists
        self._smaract_state.create_state("ENDSTOP", "Mechanical end-stop detected")

        # The channel detected an overload condition of the positioner. This will
        # disable the control-loop to prevent the positioner from overheating. As
        # soon as the internal detection level drops to a non-critical value the
        # flag is cleared.
        self._smaract_state.create_state("OVERLOAD", "Overload condition detected")

        # The channel detected an over temperature condition. This will shut down the
        # power amplifier to prevent thermal damage. As soon as the temperature drops
        # to a non-critical level the amplifier is enabled again and the flag is cleared.
        # Note that this flag is rarely raised under normal conditions and may indicate
        # improper cooling, such as a fan failure.
        self._smaract_state.create_state(
            "OVERTEMP", "Over temperature condition detected"
        )

        self._comm = get_comm(self.config.config_dict, port=self.DEFAULT_PORT)
        global_map.register(self, children_list=[self._comm])

    def initialize_hardware(self):

        self._flush_errors()

        # get the number of channels from the device
        self.nb_channels = int(self.write_read(":DEV:NOCH?"))

    def initialize_axis(self, axis):

        axis.channel = Channel(self, axis.config.get("channel", int))
        if axis.channel.channel >= self.nb_channels:
            raise ValueError(
                "This SmarAct MCS2 can only control {self.nb_channels} \
                   axes and axis {axis.name} has channel set to {axis.channel}"
            )

    def initialize_hardware_axis(self, axis):
        # Writing positioner type loses the position (even if it is the same)
        # so we only write if we know it is not the correct one.
        if "positioner_type" in axis.config.config_dict:
            new_positioner_type = PositionerType[axis.config.get("positioner_type")]
            curr_positioner_type = axis.channel.positioner_type

            if new_positioner_type != curr_positioner_type:
                axis.channel.positioner_type = new_positioner_type
        # Check if the axis has a valid position, power-on of the controller will
        # reset the positions
        if not axis.channel.is_physical_position_known:
            log_warning(
                self,
                "{0} physical position unknown (hint: do a "
                "homing to find reference mark)".format(axis.name),
            )

        # Apply power mode from config to enable, disable or power-save
        if "power_mode" in axis.config.config_dict:
            axis.channel.power_mode = axis.config.get("power_mode")

        # force closed-loop absolute versus relative position
        self.write(":MMOD 0", axis.channel.channel)

        if "hold_time" in axis.config.config_dict:
            axis.channel.hold_time = axis.config.get("hold_time", int)

    def get_axis_info(self, axis):
        status, _, _ = self.read_status(axis.channel.channel)
        ptype = axis.channel.positioner_type.name
        pmode = axis.channel.power_mode.name
        info_str = f"     channel: {axis.channel.channel} type: {ptype}\n"
        info_str += "     status:"
        info_str += f" POWER: {pmode}"
        info_str += f"    CLOOP: {status.CLOSED_LOOP_ACTIVE}"
        info_str += f"    OVERLOAD: {status.POSITIONER_OVERLOAD}\n"

        return info_str

    def __info__(self):
        """For CLI help.
        """
        info_str = "SmarAct MCS2 CONTROLLER:\n"
        info_str += f"     controller: {self._comm._host}\n"
        info_str += f"     serial #: {self.write_read(':DEV:SNUM?')}\n"
        info_str += f"     name: {self.write_read(':DEV:NAME?')}\n"

        return info_str

    def read_status(self, channel):
        status = self.write_read(":STAT?", channel)
        axis_status = SmarActMCS2Status(int(status), CHANNEL_STATUS_BITS)
        status = self.write_read(":MOD:STAT?")
        module_status = SmarActMCS2Status(int(status), MODULE_STATUS_BITS)
        status = self.write_read(":DEV:STAT?")
        device_status = SmarActMCS2Status(int(status), DEVICE_STATUS_BITS)
        return (axis_status, module_status, device_status)

    def info_status(self, channel):
        chan, mod, dev = self.read_status(channel)
        print(f"Channel status:\n{chan}")
        print(f"Module status:\n{mod}")
        print(f"Device status:\n{dev}")

    def state(self, axis):
        state = self._smaract_state.new()

        axis_status, module_status, device_status = self.read_status(
            axis.channel.channel
        )
        enabled = axis.channel.power_mode

        # set some extra states
        if axis_status.END_STOP_REACHED:
            state.set("ENDSTOP")
        if axis_status.OVER_TEMPERATURE:
            state.set("OVER_TEMPERATURE")
        if axis_status.POSITIONER_OVERLOAD:
            state.set("OVERLOAD")
        # There is no limit switch on smaract but a software end-stop detection
        if axis_status.END_STOP_REACHED:
            state.set("ENDSTOP")

        if enabled == PowerMode.Disabled:
            state.set("OFF")
        elif (
            axis_status.ACTIVELY_MOVING
            or axis_status.CALIBRATING
            or axis_status.REFERENCING
        ):
            state.set("MOVING")
        elif (
            axis_status.POSITIONER_OVERLOAD
            or axis_status.OVER_TEMPERATURE
            or axis_status.POSITIONER_FAULT
        ):
            state.set("FAULT")
        else:
            state.set("READY")

        return state

    def get_info(self, axis):
        return ""

    def stop(self, axis):
        axis.channel.stop()
        log_debug(self, "{0} sent stop".format(axis.name))

    def set_position(self, axis, pos):
        axis.channel.set_position(pos)
        return self.read_position(axis)

    def read_position(self, axis):
        return axis.channel.position

    def start_all(self, *motion_list):
        # TODO: figure out out to use soft. trigger to move multiple axis
        for motion in motion_list:
            self.start_one(motion)

    def start_one(self, motion):
        channel = motion.axis.channel
        channel.move_absolute(motion.target_pos)

    def home_search(self, axis, switch):
        # counter-clockwise if positive
        axis.channel.find_reference_mark(switch)

    def home_state(self, axis):
        if axis.channel.status.REFERENCING:
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
