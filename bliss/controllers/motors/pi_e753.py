# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.utils import object_method

from bliss.common.axis import AxisState

from . import pi_gcs
from bliss.comm.util import TCP
import gevent.lock

import sys
import time

"""
Bliss controller for ethernet PI E753 piezo controller.
Cyril Guilloud ESRF BLISS  2014-2016
"""


class PI_E753(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.cname = "E753"

    # Init of controller.
    def initialize(self):
        """
        Controller intialization : opens a single socket for all 3 axes.
        """
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        self.sock = pi_gcs.get_pi_comm(self.config, TCP)

    def finalize(self):
        """
        Closes the controller socket.
        """
        # not called at end of device server ??? :(
        # called on a new axis creation ???

        if self.sock:
            self.sock.close()

    # Init of each axis.
    def initialize_axis(self, axis):
        elog.debug("axis initialization")

        ## To purge controller.
        # try:
        #    self.sock._raw_read()
        # except:
        #    pass

        # Enables the closed-loop.
        # Can be dangerous ??? test diff between target and position before ???
        self._set_closed_loop(axis, True)

    def initialize_encoder(self, encoder):
        pass

    """
    ON / OFF
    """

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    def read_position(self, axis):
        _ans = self._get_target_pos(axis)
        elog.debug("read_position = %f" % _ans)
        return _ans

    def read_encoder(self, encoder):
        _ans = self._get_pos()
        elog.debug("read_position measured = %f" % _ans)
        return _ans

    """ VELOCITY """

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        elog.debug("set_velocity new_velocity = %f" % new_velocity)
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
            raise RuntimeError("closed loop disabled")

    """ MOVEMENTS """

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        elog.debug("start_one target_pos = %f" % motion.target_pos)
        self.send_no_ans(motion.axis, "MOV 1 %g" % motion.target_pos)

    def stop(self, axis):
        # to check : copy of current position into target position ???
        self.send_no_ans(axis, "STP")

    """ COMMUNICATIONS"""

    def send(self, axis, cmd):
        _cmd = cmd + "\n"

        _ans = self.sock.write_readline(_cmd)
        # "\n" in answer has been removed by tcp lib.

        # self.check_error()

        return _ans

    def check_error(self):
        # Check error code
        (_err_nb, _err_str) = self._get_error()
        if _err_nb != 0:
            print(":( error #%d (%s) in send_no_ans(%r)" % (_err_nb, _err_str, cmd))

    def send_no_ans(self, axis, cmd):
        _cmd = cmd + "\n"
        self.sock.write(_cmd)

        # self.check_error()

    """ RAW COMMANDS """

    def raw_write(self, com):
        self.sock.write(com)

    def raw_write_read(self, com):
        return self.sock.write_readline(com)

    def raw_write_readlines(self, com, lines):
        return "\n".join(self.sock.write_readlines("%s\n" % com, lines))

    def get_identifier(self, axis):
        return self.send(axis, "IDN?")

    """
    E753 specific
    """

    def get_voltage(self, axis):
        """ Returns voltage read from controller."""
        _ans = self.send(axis, "SVA?")
        _voltage = float(_ans[2:])
        return _voltage

    def set_voltage(self, axis, new_voltage):
        """ Sets Voltage to the controller."""
        self.send_no_ans(axis, "SVA 1 %g" % new_voltage)

    def _get_velocity(self, axis):
        """
        Returns velocity taken from controller.
        """
        _ans = self.send(axis, "VEL?")
        _velocity = float(_ans.split("=")[1])

        return _velocity

    def _get_pos(self):
        """
        Returns real position read by capacitive sensor.
        no axis parameter as _get_pos is used by encoder.... can be a problem???
        """

        _ans = self.sock.write_readline("POS?\n")
        # _ans should looks like "1=-8.45709419e+01\n"
        # "\n" removed by tcp lib.
        _pos = float(_ans[2:])
        return _pos

    """ON TARGET """

    def _get_target_pos(self, axis):
        """
        Returns last target position (setpoint value).
        """
        _ans = self.send(axis, "MOV?")

        # _ans should looks like "1=-8.45709419e+01"
        _pos = float(_ans[2:])

        return _pos

    def _get_on_target_status(self, axis):
        _ans = self.send(axis, "ONT?")

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
        _ans = self.send(axis, "SVO?")

        _status = _ans.split("=")[1]

        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            print("err _get_closed_loop_status, _ans=%r" % _ans)
            return -1

    def _set_closed_loop(self, axis, state):
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

    def _get_error(self):
        # Does not use send() to be able to call _get_error in send().
        _error_number = int(self.sock.write_readline("ERR?\n"))
        _error_str = pi_gcs.get_error_str(int(_error_number))

        return (_error_number, _error_str)

    def _stop(self, axis):
        print("????????? PI_E753.py received _stop ???")
        self.send_no_ans(axis, "STP")

    def get_info(self, axis):
        """
        Returns a set of usefull information about controller.
        Helpful to tune the device.

        Args:
            <axis> : bliss axis
        Returns:
            None
        Raises:
            ?
        """
        (error_nb, err_str) = self._get_error()
        _txt = '      ERR nb=%d  : "%s"\n' % (error_nb, err_str)

        _infos = [
            ("Identifier                 ", "IDN?\n"),
            ("Com level                  ", "CCL?\n"),
            ("Firmware name              ", "SEP? 1 0xffff0007\n"),
            ("Firmware version           ", "SEP? 1 0xffff0008\n"),
            ("Firmware description       ", "SEP? 1 0xffff000d\n"),
            ("Firmware date              ", "SEP? 1 0xffff000e\n"),
            ("Firmware developer         ", "SEP? 1 0xffff000f\n"),
            ("Real Position              ", "POS?\n"),
            ("Setpoint Position          ", "MOV?\n"),
            ("Position low limit         ", "SPA? 1 0x07000000\n"),
            ("Position High limit        ", "SPA? 1 0x07000001\n"),
            ("Velocity                   ", "VEL?\n"),
            ("On target                  ", "ONT?\n"),
            ("On target window           ", "SPA? 1 0x07000900\n"),
            ("Target tolerance           ", "SPA? 1 0X07000900\n"),
            ("Settling time              ", "SPA? 1 0X07000901\n"),
            ("Sensor Offset              ", "SPA? 1 0x02000200\n"),
            ("Sensor Gain                ", "SPA? 1 0x02000300\n"),
            ("Motion status              ", "#5\n"),
            ("Closed loop status         ", "SVO?\n"),
            ("Auto Zero Calibration ?    ", "ATZ?\n"),
            ("Analog input setpoint      ", "AOS?\n"),
            ("Low    Voltage Limit       ", "SPA? 1 0x07000A00\n"),
            ("High Voltage Limit         ", "SPA? 1 0x07000A01\n"),
        ]

        for i in _infos:
            _txt = _txt + "        %s %s\n" % (i[0], self.send(axis, i[1]))

        _txt = _txt + "        %s    \n%s\n" % (
            "Communication parameters",
            "\n".join(self.sock.write_readlines("IFC?\n", 5)),
        )

        _txt = _txt + "        %s    \n%s\n" % (
            "Analog setpoints",
            "\n".join(self.sock.write_readlines("TSP?\n", 2)),
        )

        _txt = _txt + "        %s    \n%s\n" % (
            "ADC value of analog input",
            "\n".join(self.sock.write_readlines("TAD?\n", 2)),
        )

        # ###  TAD[1]==131071  => broken cable ??
        # 131071 = pow(2,17)-1

        return _txt
