# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.utils import object_attribute_get, object_attribute_set
from bliss.common.axis import AxisState
from bliss.common.logtools import log_debug, log_info, log_warning
from bliss import global_map

from . import pi_gcs
from bliss.comm.util import TCP
import gevent.lock

import sys
import time

"""
Bliss controller for ethernet PI E753 piezo controller.
Model PI E754 should be compatible.. to be tested.
"""


class PI_E753(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

    # Init of controller.
    def initialize(self):
        """
        Controller intialization: open a single socket for all 3 axes.
        """
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        self.comm = pi_gcs.get_pi_comm(self.config, TCP)

        # Check model.
        try:
            idn_ans = self.comm.write_readline(b"*IDN?\n").decode()
            log_info(self, f"IDN?: {idn_ans}")
            if idn_ans.find("E-753") > 0:
                self.model = "E-753"
            elif idn_ans.find("E-754") > 0:
                self.model = "E-754"
            else:
                self.model = "UNKNOWN"
        except:
            self.model = "UNKNOWN"

        log_debug(self, f"model={self.model}")
        global_map.register(self, children_list=[self.comm])

    def close(self):
        if self.comm is not None:
            self.comm.close()

    def initialize_axis(self, axis):
        log_debug(self, "axis initialization")

        # Enables the closed-loop.
        # Can be dangerous ??? test diff between target and position before ???
        # self._set_closed_loop(axis, True)

    def initialize_encoder(self, encoder):
        pass

    """ ON / OFF """

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    """ Position """

    def read_position(self, axis):
        _ans = self._get_target_pos(axis)
        log_debug(self, "read_position = %f" % _ans)
        return _ans

    def read_encoder(self, encoder):
        _ans = self._get_pos()

        # log_info(self, "read encodeer")
        # log_warning(self, "read encod")
        log_debug(self, "read_position measured = %f" % _ans)
        return _ans

    """ VELOCITY """

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        """
        - <new_velocity>: 'float'
        """
        log_debug(self, "set_velocity new_velocity = %f" % new_velocity)
        self.send_no_ans(axis, "VEL 1 %f" % new_velocity)

        return self.read_velocity(axis)

    """ STATE """

    def state(self, axis):
        if self._get_closed_loop_status(axis):
            if self._get_on_target_status(axis):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            # open-loop => always ready.
            return AxisState("READY")

    """ MOVEMENTS """

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        """
        - Sends 'MOV' or 'SVA' depending on closed loop mode.

        Args:
            - <motion> : Bliss motion object.

        Return:
            - None
        """
        if self._get_closed_loop_status(motion.axis):
            # Command in position.
            self.send_no_ans(motion.axis, "MOV 1 %g" % motion.target_pos)
        else:
            # Command in voltage.
            self.send_no_ans(motion.axis, "SVA 1 %g" % motion.target_pos)

    def stop(self, axis):
        """
        * HLT -> stop smoothly
        * STP -> stop asap
        * 24    -> stop asap
        * to check : copy of current position into target position ???
        """
        self.send_no_ans(axis, "STP")

    """ COMMUNICATIONS"""

    def send(self, axis, cmd):
        """
        - Converts <cmd> into 'bytes' and sends it to controller.
        - Adds terminator to <cmd> string.
        - <axis> is passed for debugging purposes.
        - Type of <cmd> must be 'str'.
        - Type of returned string is 'str'.
        """
        log_debug(self, f"SEND: {cmd}")
        _cmd = cmd.encode() + b"\n"
        _t0 = time.time()

        _ans = self.comm.write_readline(_cmd).decode()
        # "\n" in answer has been removed by tcp lib.

        _duration = time.time() - _t0
        if _duration > 0.005:
            log_info(
                self,
                "PI_E753.py : Received %r from Send %s (duration : %g ms) "
                % (_ans, _cmd, _duration * 1000),
            )

        self.check_error(_cmd)

        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Sends <cmd> command to controller.
        - Adds terminator to <cmd> string.
        - Channel is already defined in <cmd>.
        - Type of <cmd> must be 'str'.
        - Used for answer-less commands, thus return nothing.
        """
        log_debug(self, f"SEND_NO_ANS: {cmd}")
        _cmd = cmd.encode() + b"\n"
        self.comm.write(_cmd)
        self.check_error(_cmd)

    def check_error(self, command):
        """
        - Checks error code
        - <command> : 'bytes' : string displayed in case of error
        """
        (_err_nb, _err_str) = self._get_error()
        if _err_nb != 0:
            print(":( error #%d (%s) in send_no_ans(%r)" % (_err_nb, _err_str, command))

    """
    Raw communication commands.
    To encode/decode and to be exported in Tango DS.
    """

    def raw_write(self, cmd):
        """
        - <cmd> must be 'str'
        """
        self.comm.write(cmd.encode())

    def raw_write_read(self, cmd):
        """
        - <cmd> must be 'str'
        - Return 'str'
        """
        return self.comm.write_readline(cmd.encode()).decode()

    def raw_write_readlines(self, cmd, lines):
        """
        - Add '\n' terminator to <cmd> string
        - Send <cmd> string to the controller and read back <lines> lines
        - <cmd>: 'str'
        - <lines>: 'int'
        """
        _cmd = cmd.encode() + b"\n"
        return "\n".join(self.comm.write_readlines(_cmd, lines).decode())

    """
    E753 specific
    """

    @object_method(types_info=("None", "float"))
    def get_voltage(self, axis):
        """ Return voltage read from controller."""
        _ans = self.send(axis, "SVA? 1")
        _voltage = float(_ans[2:])
        return _voltage

    @object_method(types_info=("None", "float"))
    def get_output_voltage(self, axis):
        """ Return output voltage read from controller. """
        _ans = self.send(axis, "VOL? 1")
        _voltage = float(_ans[2:])
        return _voltage

    def set_voltage(self, axis, new_voltage):
        """ Sets Voltage to the controller."""
        self.send_no_ans(axis, "SVA 1 %g" % new_voltage)

    def _get_velocity(self, axis):
        """
        Return velocity taken from controller.
        """
        _ans = self.send(axis, "VEL? 1")
        _velocity = float(_ans.split("=")[1])

        return _velocity

    def _get_pos(self):
        """
        - no axis parameter as _get_pos is used by encoder.... can be a problem???
        - Return a 'float': real position read by capacitive sensor.
        """
        _ans = self.comm.write_readline(b"POS?\n").decode()
        # _ans should looks like "1=-8.45709419e+01\n"
        # "\n" removed by tcp lib.
        _pos = float(_ans[2:])
        return _pos

    def _get_target_pos(self, axis):
        """
        Return last target position (MOV?/SVA?/VOL? command) (setpoint value).
            - SVA? : Query the commanded output voltage (voltage setpoint).
            - VOL? : Query the current output voltage (real voltage).
            - MOV? : Return the last valid commanded target position.
        """
        if self._get_closed_loop_status(axis):
            _ans = self.send(axis, "MOV? 1")
            # _ans should looks like "1=-8.45709419e+01"
            _pos = float(_ans[2:])
        else:
            _ans = self.send(axis, "SVA? 1")
            # _ans should looks like "???"
            _pos = float(_ans[2:])
        return _pos

    def _get_on_target_status(self, axis):
        _ans = self.send(axis, "ONT? 1")

        _status = _ans.split("=")[1]

        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            print("err _get_on_target_status, _ans=%r" % _ans)
            return -1

    """ CLOSED LOOP"""

    def _get_closed_loop_status(self, axis):
        _ans = self.send(axis, "SVO? 1")

        _status = _ans.split("=")[1]

        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            print("err _get_closed_loop_status, _ans=%r" % _ans)
            return -1

    def _set_closed_loop(self, axis, state):
        """
        Activate closed-loop if <state> is True.
        """
        if state:
            self.send_no_ans(axis, "SVO 1 1")
        else:
            self.send_no_ans(axis, "SVO 1 0")

    @object_method(types_info=("None", "None"))
    def open_loop(self, axis):
        self._set_closed_loop(axis, False)

    @object_method(types_info=("None", "None"))
    def close_loop(self, axis):
        self._set_closed_loop(axis, True)

    @object_attribute_get(type_info="bool")
    def get_closed_loop(self, axis):
        return self._get_closed_loop_status(axis)

    @object_attribute_set(type_info="bool")
    def set_closed_loop(self, axis, value):
        print("set_closed_loop DISALBED FOR SECURITY ... ")
        # self._set_closed_loop(axis, True)

    @object_attribute_get(type_info="str")
    def get_model(self, axis):
        return self.model

    def _get_error(self):
        """
        Does not use send() to be able to call _get_error in send().
        """

        _error_number = int(self.comm.write_readline(b"ERR?\n").decode())
        _error_str = pi_gcs.get_error_str(int(_error_number))

        return (_error_number, _error_str)

    def _stop(self, axis):
        print("????????? PI_E753.py received _stop ???")
        self.send_no_ans(axis, "STP")

    """
    ID/INFO
    """

    def get_id(self, axis):
        """
        Return controller identifier.
        """
        return self.send(axis, "*IDN?")

    def get_axis_info(self, axis):
        """Return Controller specific info about <axis>
        """
        info_str = "PI INFO:\n"
        info_str += f"     voltage (SVA) = {self.get_voltage(axis)}\n"
        info_str += f"     output voltage (VOL) = {self.get_output_voltage(axis)}\n"
        info_str += f"     closed loop = {self.get_closed_loop(axis)}\n"

        return info_str

    def __info__(self):
        info_str = f"PI {self.model}\n"
        info_str += f"     {self.comm.__info__()}"
        return info_str

    @object_method(types_info=("None", "string"))
    def get_info(self, axis):
        return self.get_hw_info()

    def get_hw_info(self):
        """
        Return a set of usefull information about controller.
        Helpful to tune the device.

        Args:
            None
        Return:
            None

        IDN? for e753:
             Physik Instrumente, E-753.1CD, 111166712, 08.00.02.00

        IDN? for e754:
             (c)2016 Physik Instrumente (PI) GmbH & Co. KG, E-754.1CD, 117045756, 1.01

        0xffff000* parameters are not valid for 754

        """

        _infos = [
            ("Identifier                 ", "*IDN?"),
            ("Com level                  ", "CCL?"),
            ("Real Position              ", "POS?"),
            ("Setpoint Position          ", "MOV?"),
            ("Position low limit         ", "SPA? 1 0x07000000"),
            ("Position High limit        ", "SPA? 1 0x07000001"),
            ("Velocity                   ", "VEL?"),
            ("On target                  ", "ONT?"),
            ("On target window           ", "SPA? 1 0x07000900"),
            ("Target tolerance           ", "SPA? 1 0X07000900"),
            ("Settling time              ", "SPA? 1 0X07000901"),
            ("Sensor Offset              ", "SPA? 1 0x02000200"),
            ("Sensor Gain                ", "SPA? 1 0x02000300"),
            ("Motion status              ", "#5"),
            ("Closed loop status         ", "SVO?"),
            ("Auto Zero Calibration ?    ", "ATZ?"),
            ("Analog input setpoint      ", "AOS?"),
            ("Low  Voltage Limit         ", "SPA? 1 0x07000A00"),
            ("High Voltage Limit         ", "SPA? 1 0x07000A01"),
        ]

        if self.model == "E-753":
            _infos.append(("Firmware name              ", "SEP? 1 0xffff0007"))
            _infos.append(("Firmware version           ", "SEP? 1 0xffff0008"))
            _infos.append(("Firmware description       ", "SEP? 1 0xffff000d"))
            _infos.append(("Firmware date              ", "SEP? 1 0xffff000e"))
            _infos.append(("Firmware developer         ", "SEP? 1 0xffff000f"))

        (error_nb, err_str) = self._get_error()
        _txt = '      ERR nb=%d  : "%s"\n' % (error_nb, err_str)

        # Reads pre-defined infos (1-line answers only)
        for i in _infos:
            _ans = self.comm.write_readline(f"{i[1]}\n".encode()).decode()
            _txt += f"        {i[0]} {_ans} \n"

        # Reads multi-lines infos.

        # IFC
        _ans = [bs.decode() for bs in self.comm.write_readlines(b"IFC?\n", 5)]
        _txt = _txt + "        %s    \n%s\n" % (
            "Communication parameters",
            "\n".join(_ans),
        )

        if self.model == "E-753":
            _tad_nb_lines = 2
            _tsp_nb_lines = 2
        elif self.model == "E-754":
            _tad_nb_lines = 3
            _tsp_nb_lines = 3

        # TSP
        _ans = [
            bs.decode() for bs in self.comm.write_readlines(b"TSP?\n", _tsp_nb_lines)
        ]
        _txt = _txt + "        %s    \n%s\n" % ("Analog setpoints", "\n".join(_ans))

        # TAD
        _ans = [
            bs.decode() for bs in self.comm.write_readlines(b"TAD?\n", _tad_nb_lines)
        ]
        _txt = _txt + "        %s    \n%s\n" % (
            "ADC value of analog input",
            "\n".join(_ans),
        )

        # ###  TAD[1]==131071  => broken cable ??
        # 131071 = pow(2,17)-1

        return _txt
