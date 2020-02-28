# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import weakref

from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.utils import object_attribute_get, object_attribute_set

from bliss.common.axis import AxisState
from bliss.common.logtools import log_info, log_debug
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
    CHAN_LETTER = {1: "A", 2: "B", 3: "C"}

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self.__axis_online = weakref.WeakKeyDictionary()
        self.__axis_closed_loop = weakref.WeakKeyDictionary()
        self.__axis_auto_gate = weakref.WeakKeyDictionary()
        self.__axis_low_limit = weakref.WeakKeyDictionary()
        self.__axis_high_limit = weakref.WeakKeyDictionary()

    def move_done_event_received(self, state, sender=None):
        # <sender> is the axis.
        log_info(
            self,
            "move_done_event_received(state=%s axis.sender=%s)",
            state,
            sender.name,
        )
        if self.__axis_auto_gate[sender]:
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
        if axis.channel not in (1, 2, 3):
            raise ValueError("PI_E51X invalid motor channel : can only be 1, 2 or 3")
        axis.chan_letter = self.CHAN_LETTER[axis.channel]

        # set online
        self.set_on(axis)

        # set velocity control mode
        self.send_no_ans(axis, "VCO %s 1" % axis.chan_letter)

        # Closed loop
        self.__axis_closed_loop[axis] = self._get_closed_loop_status(axis)
        servo_mode = axis.config.get("servo_mode", bool, None)
        if servo_mode is not None:
            if self.__axis_closed_loop[axis] != servo_mode:
                self._set_closed_loop(axis, servo_mode)

        # Drift compensation
        drift_mode = axis.config.get("drift_compensation", bool, None)
        if drift_mode is not None:
            self._set_dco(axis, int(drift_mode))

        # automatic gate (OFF by default)
        self.__axis_auto_gate[axis] = False
        # connect move_done for auto_gate mode
        event.connect(axis, "move_done", self.move_done_event_received)

        # keep limits for gate
        self.__axis_low_limit[axis] = self._get_low_limit(axis)
        self.__axis_high_limit[axis] = self._get_high_limit(axis)

    def initialize_encoder(self, encoder):
        encoder.channel = encoder.config.get("channel", int)
        if encoder.channel not in (1, 2, 3):
            raise ValueError("PI_E51X invalid motor channel : can only be 1, 2 or 3")
        encoder.chan_letter = self.CHAN_LETTER[encoder.channel]

    """
    ON / OFF
    """

    def set_on(self, axis):
        log_debug(self, "set %s ONLINE" % axis.name)
        self.send_no_ans(axis, "ONL %d 1" % axis.channel)
        self.__axis_online[axis] = 1

    def set_off(self, axis):
        log_debug(self, "set %s OFFLINE" % axis.name)
        self.send_no_ans(axis, "ONL %d 0" % axis.channel)
        self.__axis_online[axis] = 0

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
            _pos = cache["pos"]
            log_debug(self, "position setpoint cache : %r" % _pos)
        else:
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
            _pos = cache["pos"]
            log_debug(self, "position measured cache : %r" % _pos)
        else:
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

        log_debug(self, "read %s velocity : %g " % (axis.name, _velocity))
        return _velocity

    def set_velocity(self, axis, new_velocity):
        self.send_no_ans(axis, "VEL %s %f" % (axis.chan_letter, new_velocity))
        log_debug(self, "%s velocity set : %g" % (axis.name, new_velocity))
        return self.read_velocity(axis)

    def state(self, axis):
        if not self.__axis_online[axis]:
            return AxisState("OFF")
        if self.__axis_closed_loop[axis]:
            log_debug(self, "%s state: CLOSED-LOOP active" % axis.name)
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            log_debug(self, "%s state: CLOSED-LOOP is not active" % axis.name)
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
        if self.__axis_closed_loop[motion.axis]:
            log_debug(
                self,
                "Move %s in position to %g" % (motion.axis.name, motion.target_pos),
            )
            # Command in position.
            self.send_no_ans(
                motion.axis, "MOV %s %g" % (motion.axis.chan_letter, motion.target_pos)
            )
        else:
            log_debug(
                self, "Move %s in voltage to %g" % (motion.axis.name, motion.target_pos)
            )
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

        _cmd = cmd.encode() + b"\n"
        _t0 = time.time()

        _ans = self.comm.write_readline(_cmd).decode()
        # "\n" in answer has been removed by tcp lib.

        _duration = time.time() - _t0
        if _duration > 0.005:
            log_info(
                self,
                "PI_E51X.py : Received %r from Send %s (duration : %g ms)",
                _ans,
                _cmd,
                _duration * 1000,
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
        self.check_error(_cmd)

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
        if self.__axis_closed_loop[axis]:
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

    """
    DCO : Drift Compensation Offset.
    """

    @object_method(types_info=("None", "None"))
    def activate_dco(self, axis):
        self._set_dco(axis, 1)

    @object_method(types_info=("None", "None"))
    def desactivate_dco(self, axis):
        self._set_dco(axis, 0)

    @object_attribute_get(type_info="bool")
    def get_dco(self, axis):
        dco = self.send(axis, "DCO? %s" % axis.chan_letter)
        val = int(dco[2:])
        return bool(val)

    @object_method(types_info=("bool", "None"))
    def set_dco(self, axis, onoff):
        log_debug(self, "set drift compensation (dco) to %s" % onoff)
        self._set_dco(axis, onoff)

    def _set_dco(self, axis, onoff):
        self.send_no_ans(axis, "DCO %s %d" % (axis.chan_letter, onoff))

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

    """ 
    Closed loop commands
    """

    def _get_closed_loop_status(self, axis):
        """
        Returns Closed loop status (Servo state) (SVO? command)
        -> True/False
        """
        _ans = self.send(axis, "SVO? %s" % axis.chan_letter)
        _status = bool(int(_ans[2:]))
        return _status

    def _set_closed_loop(self, axis, onoff):
        log_debug(self, "set %s closed_loop to %s" % (axis.name, onoff))
        self.send_no_ans(axis, "SVO %s %d" % (axis.chan_letter, onoff))
        self.__axis_closed_loop[axis] = self._get_closed_loop_status(axis)
        log_debug(
            self, "effective closed_loop is now %s" % self.__axis_closed_loop[axis]
        )
        if self.__axis_closed_loop[axis] != onoff:
            raise RuntimeError(
                "Failed to change %s closed_loop mode to %s" % (axis.name, onoff)
            )

    def _get_on_target_status(self, axis):
        """
        Returns << On Target >> status (ONT? command).
        True/False
        """
        _ans = self.send(axis, "ONT? %s" % axis.chan_letter)
        _status = bool(int(_ans[2:]))
        return _status

    @object_method(types_info=("None", "None"))
    def open_loop(self, axis):
        self._set_closed_loop(axis, 0)

    @object_method(types_info=("None", "None"))
    def close_loop(self, axis):
        self._set_closed_loop(axis, 1)

    @object_method(types_info=("bool", "None"))
    def set_closed_loop(self, axis, onoff):
        self._set_closed_loop(axis, onoff)

    @object_attribute_get(type_info="bool")
    def get_closed_loop(self, axis):
        return self.__axis_closed_loop[axis]

    """
    Auto gate
    """

    @object_attribute_get(type_info="bool")
    def get_auto_gate(self, axis):
        """Automatic gating for continuous scan"""
        return self.__axis_auto_gate[axis]

    @object_attribute_set(type_info="bool")
    def set_auto_gate(self, axis, value):
        self.__axis_auto_gate[axis] = value is True
        log_info(
            self,
            "auto_gate is %s for axis.channel %s",
            value is True and "ON" or "OFF",
            axis.channel,
        )

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
                self.__axis_low_limit[axis],
                _ch,
                self.__axis_high_limit[axis],
                _ch,
            )
        else:
            _cmd = "CTO %d 3 3 %d 5 %g %d 6 %g %d 7 0" % (
                _ch,
                _ch,
                self.__axis_low_limit[axis],
                _ch,
                self.__axis_high_limit[axis],
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

    def __info__(self, axis=None):
        if axis is None:
            return self.get_controller_info()
        else:
            return self.get_info(axis)

    def get_controller_info(self):
        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Serial Number              ", "SSN?"),
            ("Com level                  ", "CCL?"),
            ("GCS Syntax version         ", "CSV?"),
            ("Last error code            ", "ERR?"),
        ]

        _txt = "PI_E51X controller :\n"
        # Reads pre-defined infos (1 line answers)
        for (label, cmd) in _infos:
            value = self.comm.write_readline(cmd.encode() + b"\n")
            _txt = _txt + "%s %s\n" % (label, value.decode())

        # Reads multi-lines infos.
        _ans = [bs.decode() for bs in self.comm.write_readlines(b"IFC?\n", 6)]
        _txt = _txt + "\n%s :\n%s\n" % ("Communication parameters", "\n".join(_ans))

        _ans = [bs.decode() for bs in self.comm.write_readlines(b"VER?\n", 3)]
        _txt = _txt + "\n%s :\n%s\n" % ("Firmware version", "\n".join(_ans))

        return _txt

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

        _txt = "     PI_E51X STATUS:\n"

        # Reads pre-defined infos (1 line answers)
        for i in _infos:
            _txt = _txt + "        %s %s\n" % (i[0], self.send(axis, (i[1])))

        (error_nb, err_str) = self._get_error()
        _txt += "        Last error code             %d= %s" % (error_nb, err_str)
        return _txt
