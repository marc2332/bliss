# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import numpy
import weakref
import gevent

from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.utils import add_property
from bliss.common.axis import AxisState, Motion, CyclicTrajectory
from bliss.config.channels import Cache
from bliss.common.switch import Switch as BaseSwitch
from bliss.common.logtools import log_info, log_debug, log_error

from . import pi_gcs

"""
Bliss controller for ethernet PI E712 piezo controller.
Copied from the preliminary E517 controller.
Programmed keeping in mind, that we might have a PI controller class, which could
be inherited to the E517, E712 etc.

Holger Witsch ESRF BLISS
Oct 2014

config example:
- class: PI_E712
  tcp:
    url: nscopepi712
  axes:
  - name: py
    channel: 1
    velocity: 100
    acceleration: 1.
    steps_per_unit: 1
    servo_mode: 1

  - name: px
    channel: 2
    velocity: 100
    acceleration: 1.
    steps_per_unit: 1
    servo_mode: 1
"""


class PI_E712(pi_gcs.Communication, pi_gcs.Recorder, Controller):
    def __init__(self, *args, **kwargs):
        pi_gcs.Communication.__init__(self)
        pi_gcs.Recorder.__init__(self)
        Controller.__init__(self, *args, **kwargs)

        self.cname = "E712"
        self.__axis_closed_loop = weakref.WeakKeyDictionary()

    def initialize(self):
        self.com_initialize()

    def initialize_axis(self, axis):
        """
        - Reads specific config
        - Adds specific methods
        - Switches piezo to ONLINE mode so that axis motion can be caused
          by move commands.

        Args:
            - <axis>
        Returns:
            - None
        """
        log_info(self, "initialize_axis() called for axis %r" % axis.name)

        self._hw_status = AxisState("READY")

        """ Documentation uses the word AxisID instead of channel
            Note: any function used as axis method must accept axis as an argument! Otherwise
                  you will see:
                  TypeError: check_power_cut() takes exactly 1 argument (2 given)
        """
        axis.channel = axis.config.get("channel", int)

        self._gate_enabled = False

        # Updates cached value of closed loop status.
        closed_loop_cache = Cache(axis, "closed_loop")
        self.__axis_closed_loop[axis] = closed_loop_cache
        if closed_loop_cache.value is None:
            closed_loop_cache.value = self._get_closed_loop_status(axis)

        add_property(axis, "closed_loop", lambda x: self.__axis_closed_loop[x].value)
        self.check_power_cut()

        log_debug(self, "axis = %r" % axis.name)

        self._add_recoder_enum_on_axis(axis)

        # supposed that we are on target on init
        axis._last_on_target = True

        # check servo mode (default true)
        servo_mode = axis.config.get("servo_mode", converter=None, default=True)
        if axis.closed_loop != servo_mode:
            # spawn if to avoid recursion
            gevent.spawn(self.activate_closed_loop, axis, servo_mode)

    def initialize_encoder(self, encoder):
        pass

    def read_encoder(self, encoder):
        return self._get_pos(encoder.config.get("channel", int))

    def read_position(self, axis):
        """
        Returns position's setpoint or measured position.
        Measured position command is POS?
        Setpoint position is MOV? of VOL? or SVA? depending on closed-loop
        mode is ON or OFF.

        Args:
            - <axis> : bliss axis.
            - [<measured>] : boolean : if True, function returns measured position.
        Returns:
            - <position> : float : piezo position in Micro-meters or in Volts.
        """
        if axis._last_on_target:
            _pos = self._get_target_pos(axis)
            log_debug(self, "position read : %g" % _pos)
        else:  # if moving return real position
            _pos = self._get_pos(axis.channel)

        return _pos

    """ VELOCITY """

    def read_velocity(self, axis):
        """
        """
        # _ans should look like "A=+0012.0000"
        # removes 'X=' prefix
        _velocity = float(self.command("VEL? %s" % axis.channel))
        log_debug(self, "read_velocity : %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.command("VEL %s %f" % (axis.channel, new_velocity))
        log_debug(self, "velocity set : %g" % new_velocity)
        return self.read_velocity(axis)

    def read_acceleration(self, axis):
        if hasattr(axis, "_acceleration_value"):
            return axis._acceleration_value
        else:
            return 1.

    def set_acceleration(self, axis, acceleration):
        axis._acceleration_value = acceleration

    """ STATE """

    def state(self, axis):
        log_debug(
            self, "axis.closed_loop for axis %s is %s" % (axis.name, axis.closed_loop)
        )
        with self.sock.lock:
            # check if WAV motion is active
            if self.sock.write_readline(chr(9).encode()) != b"0":
                return AxisState("MOVING")

            if axis.closed_loop:
                if self._get_on_target_status(axis):
                    return AxisState("READY")
                else:
                    return AxisState("MOVING")
            else:
                log_debug(self, "CLOSED-LOOP is False")
                # ok for open loop mode...
                return AxisState("READY")

    def check_ready_to_move(self, axis, state):
        return True  # Can always move

    """ MOVEMENTS """

    def prepare_move(self, motion):
        log_debug(self, "pass")
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """
        self.start_all(motion)

    def start_all(self, *motions):
        ###
        ###  hummm a bit dangerous to mix voltage and microns for the same command isnt'it ?
        ###
        mov_cmd = list()
        voltage_cmd = list()
        for motion in motions:
            l_cmd = mov_cmd if motion.axis.closed_loop else voltage_cmd
            l_cmd.append((motion.axis.channel, motion.target_pos))
            cmd = ""
            if mov_cmd:
                cmd += "MOV " + " ".join(
                    ["%s %g" % (chan, pos) for chan, pos in mov_cmd]
                )
            if voltage_cmd:
                if cmd:
                    cmd += "\n"
                cmd += "SVA " + " ".join(
                    ["%s %g" % (chan, pos) for chan, pos in voltage_cmd]
                )
        self.command(cmd)

    def stop(self, axis):
        self.stop_all()

    def stop_all(self, *motions):
        """
        * HLT -> stop smoothly
        * STP -> stop asap
        * 24    -> stop asap

        As the controller open the closed loop, to stop motions,
        target position change a little bit for axes which are
        already stopped. So we reset the target position for all
        stopped axes to the previous value before the stop command.
        """
        with self.sock.lock:
            channels = [
                str(x.channel).encode()
                for x in self.axes.values()
                if hasattr(x, "channel")
            ]
            channels_str = b" ".join(channels)
            cmd = b"\n".join(
                [b"%s %s" % (cmd, channels_str) for cmd in (b"ONT?", b"MOV?")]
            )
            cmd += b"\n%c" % 24  # Char to stop all movement
            reply = self.sock.write_readlines(cmd, len(channels) * 2)
            error = self.sock.write_readline(
                b"ERR?\n"
            )  # should be 10 -> Controller was stopped by command
            reply = [r.decode() for r in reply]
            channel_on_target = set()
            for channel_target in reply[: len(channels)]:
                channel, ont = channel_target.strip().split("=")
                if int(ont):
                    channel_on_target.add(channel)
            channels_position = list()
            for chan_pos in reply[len(channels) :]:
                channel, position = chan_pos.strip().split("=")
                if channel in channel_on_target:
                    channels_position.extend([channel, position])
            if channels_position:
                reset_target_cmd = "MOV " + " ".join(channels_position)
                self.command(reset_target_cmd)

    """ RAW COMMANDS """

    def get_identifier(self, axis):
        """
        Returns Identification information (`*IDN?` command).
        """
        return self.command("*IDN?")

    def __info__(self):
        idn = self.command("*IDN?")
        ifc = self.command("IFC? IPADR MACADR IPSTART", 3)
        info_str = f"{idn}\n"
        info_str += f"     MAC address : {ifc[1]}\n"
        info_str += f"     IP  address : {ifc[0]}\n"
        info_str += "     IP start    : {0}\n".format(
            ifc[2] == b"1" and "DHCP" or "STATIC"
        )
        return info_str

    def output_position_gate(self, axis, position_1, position_2, output=1):
        """
        This program an external gate on the specified output.
        If the motor position is in between the programmed positions,
        the signal is high.

        Args:
          - output by default first external output
        """
        cmd = "CTO {0} 2 {1} {0} 3 3 {0} 5 {2} {0} 6 {3} {0} 7 1".format(
            output, axis.channel, position_1, position_2
        )
        self.command(cmd)

    def has_trajectory(self):
        return True

    def prepare_trajectory(self, *trajectories):
        if not trajectories:
            raise ValueError("no trajectory provided")
        servo_cycle = float(self.command("SPA? 1 0xe000200"))
        number_of_points = int(self.command("SPA? 1 0x13000004"))
        is_cyclic_traj = isinstance(trajectories[0], CyclicTrajectory)
        pvt = trajectories[0].pvt_pattern if is_cyclic_traj else trajectories[0].pvt
        last_time = pvt["time"][-1]
        calc_servo_cycle = (last_time * len(trajectories)) / number_of_points
        table_generator_rate = int(numpy.ceil(calc_servo_cycle / servo_cycle))
        servo_cycle *= table_generator_rate
        nb_traj_cycles = trajectories[0].nb_cycles if is_cyclic_traj else 1
        commmands = [
            "TWC",  # clear trig settings
            "WTR 0 {} 1".format(table_generator_rate),
            "WGC 1 {}".format(nb_traj_cycles),
        ]
        for traj in trajectories:
            pvt = traj.pvt_pattern if is_cyclic_traj else traj.pvt
            time = pvt["time"]
            positions = pvt["position"]
            velocities = pvt["velocity"]
            axis = traj.axis
            cmd_format = "WAV %d " % axis.channel
            cmd_format += "{cont} LIN {seglength} {amp} " "{offset} {seglength} {startpoint} {speed_up_down}"
            commmands.append("WSL {channel} {channel}".format(channel=axis.channel))
            offset = traj.origin if is_cyclic_traj else 0
            commmands.append(
                "WOS {channel} {offset}".format(channel=axis.channel, offset=offset)
            )
            cont = "X"
            index = 0
            while True:
                try:
                    p1, v1, t1 = positions[index], velocities[index], time[index]
                except IndexError:  # End loop
                    break

                try:
                    p2, v2, t2 = (
                        positions[index + 1],
                        velocities[index + 1],
                        time[index + 1],
                    )
                except IndexError:  # End loop
                    break
                # default
                start_time = t1
                end_time = t2
                start_position = p1
                end_position = p2
                speed_up_down = 0
                inc_index = 1
                try:
                    p3, v3, t3 = (
                        positions[index + 2],
                        velocities[index + 2],
                        time[index + 2],
                    )
                except IndexError:
                    pass
                else:
                    try:
                        p4, v4, t4 = (
                            positions[index + 3],
                            velocities[index + 3],
                            time[index + 3],
                        )
                    except IndexError:
                        if abs(v1 - v3) < 1e-6 and abs(v2 - v1) > 1e-6:
                            start_time = t1
                            end_time = t3
                            start_position = p1
                            end_position = p3
                            speed_up_down = min(t2 - t1, t3 - t2)
                    else:
                        if abs(v1 - v4) < 1e-6 and abs(v2 - v3) < 1e-6:
                            start_time = t1
                            end_time = t4
                            start_position = p1
                            end_position = p4
                            speed_up_down = min(t2 - t1, t4 - t3)
                            inc_index = 3
                        elif abs(v1 - v3) < 1e-6 and abs(v2 - v1) > 1e-6:
                            start_time = t1
                            end_time = t3
                            start_position = p1
                            end_position = p3
                            speed_up_down = min(t2 - t1, t3 - t2)
                            inc_index = 2

                index += inc_index
                start_time /= servo_cycle
                end_time /= servo_cycle
                seglength = int(end_time - start_time)
                if seglength <= 0:
                    continue
                speed_up_down = int(speed_up_down / servo_cycle)
                if speed_up_down > seglength / 2.:
                    speed_up_down = seglength / 2.
                start_time = start_time if cont == "X" else 0
                cmd = cmd_format.format(
                    cont=cont,
                    seglength=seglength,
                    amp=end_position - start_position,
                    offset=start_position,
                    startpoint=int(start_time),
                    speed_up_down=speed_up_down,
                )
                commmands.append(cmd)
                cont = "&"
            # trajectories events
            events = (
                traj.events_pattern_positions
                if is_cyclic_traj
                else traj.events_positions
            )
            for evt in events:
                commmands.append(
                    "TWS 1 %d 1" % (int((evt["time"] // servo_cycle) + 1.5))
                )

        for cmd in commmands:
            self.command(cmd)

    def has_trajectory_event(self):
        return True

    def set_trajectory_events(self, *trajectories):
        # In prepare_trajectory we programmed the trigger positions
        # (see TWC and TWS command)
        # Just link external trigger with programmed TWS
        self.command("CTO 1 3 4")

    def move_to_trajectory(self, *trajectories):
        motions = [Motion(t.axis, t.pvt["position"][0], 0) for t in trajectories]
        self.start_all(*motions)

    def start_trajectory(self, *trajectories):
        is_cyclic_traj = isinstance(trajectories[0], CyclicTrajectory)
        mode = 0x101 if is_cyclic_traj else 0x1
        axes_str = " ".join(["%d %d" % (t.axis.channel, mode) for t in trajectories])
        self.command("WGO " + axes_str)

    def stop_trajectory(self, *trajectories):
        axes_str = " ".join(["%d 0" % t.axis.channel for t in trajectories])
        self.command("WGO " + axes_str)

    def _get_pos(self, channel):
        """
        Args:
            - <axis> :
        Returns:
            - <position> Returns real position (POS? command) 

        Raises:
            ?
        """
        _pos = float(self.command("POS? %d" % channel))

        return _pos

    def _get_target_pos(self, axis):
        """
        Returns last valid position setpoint ('MOV?' command).
        """
        if axis.closed_loop:
            _ans = self.command("MOV? %s" % axis.channel)
        else:
            _ans = self.command("SVA? %s" % axis.channel)

        return float(_ans)

    def _get_target_voltage(self, axis):
        """
        Returns last valid voltage setpoint ('SVA?' command).
        """
        return float(self.command("SVA? %s" % axis.channel))

    def _get_voltage(self, axis):
        """
        Returns Read Voltage Of Output Signal Channel (VOL? command)
        """
        return float(self.command("VOL? %s" % axis.channel))

    @object_method(types_info=("bool", "None"))
    def activate_closed_loop(self, axis, onoff=True):
        """
        Activate/Desactivate closed loop status (Servo state) (SVO command)
        """
        self.command("SVO %s %d" % (axis.channel, onoff))
        log_debug(self, "Piezo Servo %r" % onoff)

        # Only when closing loop: waits to be ON-Target.
        if onoff:
            _t0 = time.time()
            cl_timeout = .5

            _ont_state = self._get_on_target_status(axis)
            log_info(self, "axis {0:s} waiting to be ONTARGET".format(axis.name))
            while (not _ont_state) and (time.time() - _t0) < cl_timeout:
                time.sleep(0.01)
                _ont_state = self._get_on_target_status(axis)
            if not _ont_state:
                log_error(self, "axis {0:s} NOT on-target".format(axis.name))
                raise RuntimeError(
                    "Unable to close the loop : "
                    "not ON-TARGET after %gs :( " % cl_timeout
                )
            else:
                log_info(
                    self,
                    "axis {0:s} ONT ok after {1:g} s".format(
                        axis.name, time.time() - _t0
                    ),
                )

        # Updates bliss setting (internal cached) position.
        self.__axis_closed_loop[axis].value = onoff

        axis._update_dial()

    def _get_closed_loop_status(self, axis):
        """
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        """
        return bool(int(self.command("SVO? %s" % axis.channel)))

    def _get_on_target_status(self, axis):
        """
        -

        Args:
            - <>
        Returns:
            -
        Raises:
            - ?
        """
        """
        Returns On Target status (ONT? command).
        True/False
        """
        last_on_target = bool(int(self.command("ONT? %s" % axis.channel)))
        axis._last_on_target = last_on_target
        return last_on_target

    @object_method(types_info=("None", "string"))
    def get_info(self, axis):
        """ Return hw info
        Used by tango DS
        """
        return self.get_hw_info(axis)

    @object_method(types_info=("None", "None"))
    def dump_param(self, axis):
        """ Print hw info
        """
        print(self.get_hw_info(axis))

    def get_hw_info(self, axis):
        """
        Return a set of information about controller.
        Helpful to tune the device.

        Args:
            <axis> : bliss axis
        """
        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Stage serial number        ", "SPA? %s 0xf000200" % axis.channel),
            ("Com level                  ", "CCL?"),
            ("GCS Syntax version         ", "CSV?"),
            ("Last error code            ", "ERR?"),
            ("Real Position              ", "POS? %s" % axis.channel),
            ("Closed loop status         ", "SVO? %s" % axis.channel),
            ("Output Voltage             ", "VOL? %s" % axis.channel),
            ("Setpoint Position          ", "MOV? %s" % axis.channel),
            ("On target                  ", "ONT? %s" % axis.channel),
            ("On target window           ", "SPA? %s 0x7000900" % axis.channel),
            ("On target settling time    ", "SPA? %s 0x7000901" % axis.channel),
            ("ADC Value of input signal  ", "TAD? %s" % axis.channel),
            ("Input Signal Position value", "TSP? %s" % axis.channel),
            ("Velocity                   ", "VEL? %s" % axis.channel),
            ("sensor Offset              ", "SPA? %s 0x2000200" % axis.channel),
            ("sensor Gain                ", "SPA? %s 0x2000300" % axis.channel),
            ("sensor gain 2nd order      ", "SPA? %s 0x2000400" % axis.channel),
            ("sensor gain 3rd order      ", "SPA? %s 0x2000500" % axis.channel),
            ("sensor gain 4th order      ", "SPA? %s 0x2000600" % axis.channel),
            ("Digital filter type        ", "SPA? %s 0x5000000" % axis.channel),
            ("Digital filter Bandwidth   ", "SPA? %s 0x5000001" % axis.channel),
            ("Digital filter order       ", "SPA? %s 0x5000002" % axis.channel),
            ("Range limit min            ", "SPA? %s 0x7000000" % axis.channel),
            ("Range limit max            ", "SPA? %s 0x7000001" % axis.channel),
        ]

        _txt = ""

        for text, cmd in _infos:
            _txt = _txt + "    %s %s\n" % (text, self.command(cmd))

        return _txt

    def check_power_cut(self):
        """
        checks if command level is on 1, if 0 means power has been cut
        in that case, set command level to 1
        """
        _ans = self.command("CCL?")  # get command level
        log_debug(self, "command_level was : %d " % int(_ans))
        if _ans == "0":
            self.command("CCL 1 advanced")

    def get_sensor_coeffs(self, axis):
        """
        Returns a list with sensor coefficients:
        * Offset
        * Gain constant order
        * Gain 2nd order
        * Gain 3rd order
        * Gain 4th order
        """
        commands = "\n".join(
            ("SPA? %d 0x2000%d00" % (axis.channel, i + 2)) for i in range(5)
        )
        axis.coeffs = [float(x) for x in self.command(commands, 5)]
        return axis.coeffs

    def set_sensor_coeffs(self, axis, coeff, value):
        """
        Needed, when in the table, when sensor works the opposite way
        Returns a list with sensor coefficients:
        * Offset
        * Gain constant order
        * Gain 2nd order
        * Gain 3rd order
        * Gain 4th order
        """
        self.command("SPA %s 0x2000%d00 %f" % (axis.channel, coeff + 2, value))

    def _get_tns(self, axis):
        """Get Normalized Input Signal Value. Loop 10 times to straighten out noise"""
        accu = 0
        for _ in range(10):
            time.sleep(0.01)
            _ans = self.command("TNS? %s" % axis.channel)
            # log_debug(self, "TNS? %d : %r" % (axis.channel, _ans))
            if _ans != "0":
                accu += float(_ans)
                accu /= 2
        log_debug(self, "TNS? %r", accu)
        # during tests with the piezojack, problems with a blocked socket
        # towards the controller were encountered. Usually, that was
        # manifesting with 0 TNS readings. If The accumulated value of
        # TNS is 0, we're pretty sure the connection is broken.
        # Use self.finalize() to close the socket, it should be reopened
        # by the next communication attempt.
        if accu == 0:
            log_info(
                self,
                "%s##########################################################%s"
                % (bcolors.GREEN + bcolors.BOLD, bcolors.ENDC),
            )
            log_info(
                self,
                "%sPIEZO READ TNS, accu is zero, resetting socket connection!%s"
                % (bcolors.GREEN + bcolors.BOLD, bcolors.ENDC),
            )
            log_info(
                self,
                "%s##########################################################%s"
                % (bcolors.GREEN + bcolors.BOLD, bcolors.ENDC),
            )
            self.finalize()
        return accu

    def _get_tsp(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("TSP? %s" % axis.channel)
        log_debug(self, "TSP? %s" % _ans)
        return float(_ans)

    def _get_sva(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("SVA? %s" % axis.channel)
        log_debug(self, "SVA? %s" % _ans)
        return float(_ans)

    def _get_vol(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("VOL? %s" % axis.channel)
        log_debug(self, "VOL? %s" % _ans)
        return float(_ans)

    def _get_mov(self, axis):
        """Get Input Signal Position Value"""
        _ans = self.command("MOV? %s" % axis.channel)
        log_debug(self, "MOV? %s" % _ans)
        return float(_ans)

    def _get_offset(self, axis):
        """read the offset SPA? 4 0x2000200 will yield 4 0x2000200=0.yxyxyxy+00"""
        return float(self.command("SPA? %s 0x2000200" % axis.channel))

    def _put_offset(self, axis, value):
        """write offset"""
        self.command("SPA %s 0x2000200 %f" % (axis.channel, value))
        axis.coeffs[0] = value

    def _get_tad(self, axis):
        """ TAD? delivers the ADC value"""

        accu = 0
        for _ in range(10):
            time.sleep(0.01)
            _ans = self.command("TAD? %s" % axis.channel)
            if _ans != "0":
                accu += float(_ans)
                accu /= 2
        log_debug(self, "TAD? %r" % accu)
        return accu


class bcolors:
    CSI = "\x1B["
    BOLD = CSI + "1m"
    GREY = CSI + "100m"
    RED = CSI + "101m"
    GREEN = CSI + "102m"
    YELLOW = CSI + "103m"
    BLUE = CSI + "104m"
    MAGENTA = CSI + "105m"
    LIGHTBLUE = CSI + "106m"
    WHITE = CSI + "107m"
    ENDC = CSI + "0m"


class Switch(BaseSwitch):
    """
    Switch for PI_E712 Analog and piezo amplifier Outputs

    Basic configuration:

    .. code-block::

        name: pi_switch0
        output-channel: 5       # 5 (first analogue output) 1 (first piezo amplifier)
        output-type: POSITION   # POSITION (default) or CONTROL_VOLTAGE
        output-range: [-10,10]  # -10 Volts to 10 Volts is the default
    """

    def __init__(self, name, controller, config):
        BaseSwitch.__init__(self, name, config)
        self.__controller = weakref.proxy(controller)
        self.__output_channel = None
        self.__output_type = None
        self.__output_range = None
        self.__axes = weakref.WeakValueDictionary()

    def _init(self):
        config = self.config
        try:
            self.__output_channel = config["output-channel"]
        except KeyError:
            raise KeyError(
                "output-channel is mandatory in switch '{}` "
                "in PI_E712 **{}**".format(self.name, self.__controller.name)
            )
        possible_type = {"POSITION": 2, "CONTROL_VOLTAGE": 1}
        output_type = config.get("output-type", "POSITION").upper()
        if output_type not in possible_type:
            raise ValueError("output-type can only be: %s" % possible_type)
        self.__output_type = possible_type.get(output_type)
        self.__output_range = config.get("output-range", [-10, 10])
        self.__axes = weakref.WeakValueDictionary(
            {name.upper(): axis for name, axis in self.__controller._axes.items()}
        )

    def _set(self, state):
        config = self.config
        if state == "DISABLED":  # DON'T KNOW HOW TO DISABLE
            return
        axis = self.__axes.get(state)
        if axis is None:
            raise ValueError(
                "State %s doesn't exist in the switch %s" % (state, self.name)
            )
        with self.__controller.sock.lock:
            low_position = float(
                self.__controller.command("TMN? {}".format(axis.channel))
            )
            high_position = float(
                self.__controller.command("TMX? {}".format(axis.channel))
            )
            low_voltage, high_voltage = self.__output_range
            position_scaling = round(
                ((float(high_voltage) - low_voltage) / (high_position - low_position)),
                3,
            )
            position_offset = low_voltage / position_scaling

            position_scaling *= config.get("output-correction", 1.)
            self.__controller.command(
                "SPA {axis_channel} 0x7001005 {position_scaling}".format(
                    axis_channel=axis.channel, position_scaling=position_scaling
                )
            )
            self.__controller.command(
                "SPA {axis_channel} 0x7001006 {position_offset}".format(
                    axis_channel=axis.channel, position_offset=position_offset
                )
            )
            # Link the output to the axis
            self.__controller.command(
                "SPA {output_chan} 0xA000003 {output_type}".format(
                    output_chan=self.__output_channel, output_type=self.__output_type
                )
            )
            self.__controller.command(
                "SPA {output_chan} 0xA000004 {axis_channel}".format(
                    output_chan=self.__output_channel, axis_channel=axis.channel
                )
            )

    def _get(self):
        axis_channel = int(
            self.__controller.command(
                "SPA? {output_chan} 0xa000004".format(output_chan=self.__output_channel)
            )
        )
        for name, axis in self.__axes.items():
            if axis.channel == axis_channel:
                return name
        return "DISABLED"

    def _states_list(self):
        return list(self.__axes.keys()) + ["DISABLED"]

    @property
    def scaling_and_offset(self):
        config = self.config
        self.init()
        with self.__controller.sock.lock:
            axis_channel = int(
                self.__controller.command(
                    "SPA? {output_chan} 0xa000004".format(
                        output_chan=self.__output_channel
                    )
                )
            )
            scaling = float(
                self.__controller.command(
                    "SPA? {axis_channel} 0x7001005".format(axis_channel=axis_channel)
                )
            )
            offset = float(
                self.__controller.command(
                    "SPA? {axis_channel} 0x7001006".format(axis_channel=axis_channel)
                )
            )
            scaling /= config.get("output-correction", 1.)
            return scaling, offset
