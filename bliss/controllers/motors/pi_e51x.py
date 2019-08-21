# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
from warnings import warn

from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.common.logtools import *
from bliss import global_map

from . import pi_gcs
from bliss.comm.util import TCP
from bliss.common import event

"""
Bliss controller for ethernet PI E51X piezo controller.
Base controller for E517 and E518
Cyril Guilloud ESRF BLISS
Thu 13 Feb 2014 15:51:41
"""


class PI_E51X(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

    def move_done_event_received(self, state, sender=None):
        # <sender> is the axis.
        log_info(
            self,
            "move_done_event_received(state=%s axis.sender=%s)" % (state, sender.name),
        )
        if self.auto_gate_enabled:
            if state is True:
                log_info(self, "PI_E51X.py : movement is finished")
                self.set_gate(sender, 0)
                log_debug(self, "mvt finished, gate set to 0")
            else:
                log_info(self, "PI_E51X.py : movement is starting")
                self.set_gate(sender, 1)
                log_debug(self, "mvt started, gate set to 1")

    def initialize(self):
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        self.comm = pi_gcs.get_pi_comm(self.config, TCP)

        global_map.register(self, children_list=[self.comm])

    def close(self):
        if self.comm is not None:
            self.comm.close()

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
        axis.channel = axis.config.get("channel", int)
        axis.chan_letter = axis.config.get("chan_letter")

        if axis.channel == 1:
            self.ctrl_axis = axis

        # NO automatic gating by default.
        self.auto_gate_enabled = False

        """end of move event"""
        event.connect(axis, "move_done", self.move_done_event_received)

        self.send_no_ans(axis, "ONL %d 1" % axis.channel)

        # VCO for velocity control mode ?
        # self.send_no_ans(axis, "VCO %d 1" % axis.channel)

        # Updates cached value of closed loop status.
        self.closed_loop = self._get_closed_loop_status(axis)

        # Reads high/low limits of the piezo to use in set_gate
        self.low_limit = self._get_low_limit(axis)
        self.high_limit = self._get_high_limit(axis)

    def initialize_encoder(self, encoder):
        encoder.channel = encoder.config.get("channel", int)
        encoder.chan_letter = encoder.config.get("chan_letter")

    """
    ON / OFF
    """

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    def read_position(
        self, axis, last_read={"t": time.time(), "pos": [None, None, None]}
    ):
        """
        Return position's setpoint for <axis>.
        Setpoint position is MOV? of SVA? depending on closed-loop
        mode is ON or OFF.

        Args:
            - <axis> : bliss axis.
        Returns:
            - <position> : float : piezo position in Micro-meters or in Volts.
        """
        cache = last_read

        if time.time() - cache["t"] < 0.005:
            # print "en cache not meas %f" % time.time()
            _pos = cache["pos"]
        else:
            # print "PAS encache not meas %f" % time.time()
            _pos = self._get_target_pos(axis)
            cache["pos"] = _pos
            cache["t"] = time.time()
        log_debug(self, "position setpoint read : %r" % _pos)

        return _pos[axis.channel - 1]

    def read_encoder(
        self, encoder, last_read={"t": time.time(), "pos": [None, None, None]}
    ):
        cache = last_read

        if time.time() - cache["t"] < 0.005:
            # print "encache meas %f" % time.time()
            _pos = cache["pos"]
        else:
            # print "PAS encache meas %f" % time.time()
            _pos = self._get_pos()
            cache["pos"] = _pos
            cache["t"] = time.time()
        log_debug(self, "position measured read : %r" % _pos)

        return _pos[encoder.channel - 1]

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float
        """
        _ans = self.send(axis, "VEL? %s" % axis.chan_letter)
        # _ans should looks like "A=+0012.0000"
        # removes 'X=' prefix
        _velocity = float(_ans[2:])

        log_debug(self, "read_velocity : %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.send_no_ans(axis, "VEL %s %f" % (axis.chan_letter, new_velocity))
        log_debug(self, "velocity set : %g" % new_velocity)
        return self.read_velocity(axis)

    def state(self, axis):
        # if self._get_closed_loop_status(axis):
        if self.closed_loop:
            # log_debug(self, "CLOSED-LOOP is active")
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            log_debug(self, "CLOSED-LOOP is not active")
            return AxisState("READY")

    def prepare_move(self, motion):
        """
        - TODO for multiple move...
        """
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """
        if self.closed_loop:
            # Command in position.
            self.send_no_ans(
                motion.axis, "MOV %s %g" % (motion.axis.chan_letter, motion.target_pos)
            )
        else:
            # Command in voltage.
            self.send_no_ans(
                motion.axis, "SVA %s %g" % (motion.axis.chan_letter, motion.target_pos)
            )

    def stop(self, axis):
        """
        * HLT -> stop smoothly
        * STP -> stop asap
        * 24    -> stop asap
        * to check : copy of current position into target position ???
        """
        self.send_no_ans(axis, "HLT %s" % axis.chan_letter)

        # self.comm.write(b"STP\n")

    """
    Raw communication commands
    """

    def raw_write(self, cmd):
        """
        - <cmd> must be 'str'
        """
        self.comm.write(cmd.encode())

    def raw_write_read(self, cmd):
        """
        - <cmd> must be 'str'
        - Returns 'str'
        """
        return self.comm.write_readline(cmd.encode()).decode()

    def raw_write_readlines(self, cmd, lines):
        """
        - Adds '\n' terminator to <cmd> string
        - Sends <cmd> string to the controller and read back <lines> lines
        - <cmd>: 'str'
        - <lines>: 'int'
        """
        _cmd = cmd.encode() + b"\n"
        return "\n".join(self.comm.write_readlines(_cmd, lines).decode())

    """
    E51x communications
    """

    def send(self, axis, cmd):
        """
        - Converts <cmd> into 'bytes' and sends it to controller.
        - Adds terminator to <cmd> string.
        - <axis> is passed for debugging purposes.
        - Channel must be defined in <cmd>.
        - Returns the answer from controller.
        - Type of <cmd> must be 'str'.
        - Type of returned string is 'str'.
        """
        # print( f"SEND: {cmd}")

        _cmd = cmd.encode() + b"\n"
        _t0 = time.time()

        _ans = self.comm.write_readline(_cmd).decode()
        # "\n" in answer has been removed by tcp lib.
        # print( f"RECV: {_ans}")

        _duration = time.time() - _t0
        if _duration > 0.005:
            log_info(
                self,
                "PI_E51X.py : Received %r from Send %s (duration : %g ms) "
                % (_ans, _cmd, _duration * 1000),
            )

        self.check_error(_cmd)

        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Adds the 'newline' terminator character : "\\\\n"
        - Sends command <cmd> to the PI E51X controller.
        - Channel is already defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Used for answer-less commands, thus returns nothing.
        """
        _cmd = cmd.encode() + b"\n"
        self.comm.write(_cmd)
        self.check_error(axis)

    def check_error(self, command):
        """
        - Checks error code
        - <command> : 'str' : displayed in case of error
        """
        (_err_nb, _err_str) = self._get_error()
        if _err_nb != 0:
            print(":( error #%d (%s) in send_no_ans(%r)" % (_err_nb, _err_str, command))

    """
    E51X specific
    """

    def _get_pos(self):
        """
        Args:
            - <axis> :
        Returns:
            - <position> Returns real position (POS? command) read by capacitive sensor.

        Raises:
            ?
        """
        _bs_ans = self.comm.write_readlines(b"POS?\n", 3)
        _ans = [bs.decode() for bs in _bs_ans]

        _pos = list(map(float, [x[2:] for x in _ans]))

        return _pos

    def _get_target_pos(self, axis):
        """Return last targets positions for all 3 axes.
            - (MOV?/SVA? command) (setpoint value).
            - SVA? : Query the commanded output voltage (voltage setpoint).
            - MOV? : Return the last valid commanded target position.
        Args:
            - <>
        Return:
            - list of float
        """
        if self.closed_loop:
            _bs_ans = self.comm.write_readlines(b"MOV?\n", 3)
        else:
            _bs_ans = self.comm.write_readlines(b"SVA?\n", 3)

        _ans = [bs.decode() for bs in _bs_ans]

        # _pos = float(_ans[2:])
        _pos = list(map(float, [x[2:] for x in _ans]))
        return _pos

    def _get_low_limit(self, axis):
        _ans = self.send(axis, "NLM? %s" % axis.chan_letter)
        # A=+0000.0000
        return float(_ans[2:])

    def _get_high_limit(self, axis):
        _ans = self.send(axis, "PLM? %s" % axis.chan_letter)
        # A=+0035.0000
        return float(_ans[2:])

    @object_method(types_info=("None", "None"))
    def open_loop(self, axis):
        self.send_no_ans(axis, "SVO %s 0" % axis.chan_letter)

    @object_method(types_info=("None", "None"))
    def close_loop(self, axis):
        self.send_no_ans(axis, "SVO %s 1" % axis.chan_letter)

    """
    DCO : Drift Compensation Offset.
    """

    @object_method(types_info=("None", "None"))
    def activate_dco(self, axis):
        self.send_no_ans(axis, "DCO %s 1" % axis.chan_letter)

    @object_method(types_info=("None", "None"))
    def desactivate_dco(self, axis):
        self.send_no_ans(axis, "DCO %s 0" % axis.chan_letter)

    """
    Voltage commands
    """

    def _get_voltage(self, axis):
        """
        Returns Voltage Of Output Signal Channel (VOL? command)
        """
        _ans = self.send(axis, "VOL? %s" % axis.channel)
        _vol = float(_ans.split("=+")[-1])
        return _vol

    def _get_closed_loop_status(self, axis):
        """
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        """
        _ans = self.send(axis, "SVO? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    def _get_on_target_status(self, axis):
        """
        Returns << On Target >> status (ONT? command).
        True/False
        """
        _ans = self.send(axis, "ONT? %s" % axis.chan_letter)
        _status = float(_ans[2:])

        if _status == 1:
            return True
        else:
            return False

    @object_method(types_info=("bool", "None"))
    def enable_auto_gate(self, axis, value):
        if value:
            # auto gating
            self.auto_gate_enabled = True
            log_info(
                self,
                "PI_E51X.py : enable_gate %s for axis.channel %s "
                % (str(value), axis.channel),
            )
        else:
            self.auto_gate_enabled = False

    @object_method(types_info=("bool", "None"))
    def set_gate(self, axis, state):
        """
        CTO  [<TrigOutID> <CTOPam> <Value>]+
         - <TrigOutID> : {1, 2, 3}
         - <CTOPam> :
             - 3: trigger mode
                      - <Value> : {0, 2, 3, 4}
                      - 0 : position distance
                      - 2 : OnTarget
                      - 3 : MinMaxThreshold   <----
                      - 4 : Wave Generator
             - 5: min threshold   <--- must be greater than low limit
             - 6: max threshold   <--- must be lower than high limit
             - 7: polarity : 0 / 1


        ex :      ID trigmod min/max       ID min       ID max       ID pol +
              CTO 1  3       3             1  5   0     1  6   100   1  7   1

        Args:
            - <state> : True / False
        Returns:
            -
        Raises:
            ?
        """
        _ch = axis.channel
        if state:
            _cmd = "CTO %d 3 3 %d 5 %g %d 6 %g %d 7 1" % (
                _ch,
                _ch,
                self.low_limit,
                _ch,
                self.high_limit,
                _ch,
            )
        else:
            _cmd = "CTO %d 3 3 %d 5 %g %d 6 %g %d 7 0" % (
                _ch,
                _ch,
                self.low_limit,
                _ch,
                self.high_limit,
                _ch,
            )

        log_debug(self, "set_gate :  _cmd = %s" % _cmd)

        self.send_no_ans(axis, _cmd)

    def _get_error(self):
        """
        - Checks error code
        - <command> : 'bytes' : Previous command string displayed in case of error
        """
        # Does not use send() to be able to call _get_error in send().
        _error_number = int(self.comm.write_readline(b"ERR?\n").decode())
        _error_str = pi_gcs.get_error_str(int(_error_number))

        return (_error_number, _error_str)

    """
    ID/INFO
    """

    def get_id(self, axis):
        """
        - Returns a 'str' string.
        """
        return self.send(axis, "*IDN?")

    def get_info(self, axis):
        """
        Returns a set of usefull information about controller.
        Helpful to tune the device.

        Args:
            <axis> : bliss axis
        Returns:
            None
        """
        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Serial Number              ", "SSN?"),
            ("Com level                  ", "CCL?"),
            ("GCS Syntax version         ", "CSV?"),
            ("Last error code            ", "ERR?"),
            ("Real Position              ", "POS? %s" % axis.chan_letter),
            ("Position low limit         ", "NLM? %s" % axis.chan_letter),
            ("Position high limit        ", "PLM? %s" % axis.chan_letter),
            ("Closed loop status         ", "SVO? %s" % axis.chan_letter),
            ("Voltage output high limit  ", "VMA? %s" % axis.channel),
            ("Voltage output low limit   ", "VMI? %s" % axis.channel),
            ("Output Voltage             ", "VOL? %s" % axis.channel),
            ("Setpoint Position          ", "MOV? %s" % axis.chan_letter),
            ("Drift compensation Offset  ", "DCO? %s" % axis.chan_letter),
            ("Online                     ", "ONL? %s" % axis.channel),
            ("On target                  ", "ONT? %s" % axis.chan_letter),
            ("On target window           ", "SPA? %s 0x07000900" % axis.channel),
            ("ADC Value of input signal  ", "TAD? %s" % axis.channel),
            ("Input Signal Position value", "TSP? %s" % axis.channel),
            ("Velocity control mode      ", "VCO? %s" % axis.chan_letter),
            ("Velocity                   ", "VEL? %s" % axis.chan_letter),
            ("Osensor                    ", "SPA? %s 0x02000200" % axis.channel),
            ("Ksensor                    ", "SPA? %s 0x02000300" % axis.channel),
            ("Digital filter type        ", "SPA? %s 0x05000000" % axis.channel),
            ("Digital filter Bandwidth   ", "SPA? %s 0x05000001" % axis.channel),
            ("Digital filter order       ", "SPA? %s 0x05000002" % axis.channel),
        ]

        (error_nb, err_str) = self._get_error()
        _txt = '      ERR nb=%d  : "%s"\n' % (error_nb, err_str)

        # Reads pre-defined infos (1 line answers)
        for i in _infos:
            _txt = _txt + "        %s %s\n" % (i[0], self.send(axis, (i[1])))
            # time.sleep(0.01)

        # Reads multi-lines infos.
        _ans = [bs.decode() for bs in self.comm.write_readlines(b"IFC?\n", 6)]
        _txt = _txt + "        %s    \n%s\n" % (
            "Communication parameters",
            "\n".join(_ans),
        )

        _ans = [bs.decode() for bs in self.comm.write_readlines(b"VER?\n", 3)]
        _txt = _txt + "    %s  \n%s\n" % ("Firmware version", "\n".join(_ans))

        return _txt
