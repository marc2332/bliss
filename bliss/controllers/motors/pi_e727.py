# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.utils import object_method

from bliss.common.axis import AxisState

import pi_gcs
from bliss.comm.util import TCP
import gevent.lock

import sys
import time

"""
Bliss controller for ethernet PI E727 piezo controller.
CG+MP ESRF BLISS  2014-2017
"""


class PI_E727(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self.cname = "E727"

    # Init of controller.
    def initialize(self):
        """
        Controller intialization : opens a single socket for all 3 axes.
        """

        self.trace("controller initialize")
        self.host = self.config.get("host")
        self.trace("opening socket")
        self.sock = pi_gcs.get_pi_comm(self.config, TCP)

        # just in case
        self.sock.flush()

    def finalize(self):
        """
        Closes the controller socket.
        """
        # not called at end of device server ??? :(
        # called on a new axis creation ???
        self.trace("controller finalize")
        try:
            self.trace("closing socket")
            self.sock.close()
        except:
            pass

    def trace(self, str):
        elog.debug("{s:{c}<{n}}".format(s=str, n=80, c="-"))

    # Init of each axis.
    def initialize_axis(self, axis):
        self.trace("axis initialization")

        axis.channel = axis.config.get("channel", int)

        # check communication
        try:
            _ans = self.get_identifier(axis, 0.1)
        except Exception as ex:
            _str = '%r\nERROR on "%s": switch on the controller' % (ex, self.host)
            # by default, an exception will be raised
            elog.error(_str)

        # Enables the closed-loop.
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
        _ans = self._get_pos(axis)
        elog.debug("read_position measured = %f" % _ans)
        return _ans

    """ VELOCITY """

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        elog.debug("set_velocity new_velocity = %f" % new_velocity)
        _cmd = "VEL %s %f" % (axis.channel, new_velocity)
        self.send_no_ans(axis, _cmd)
        self.check_error(_cmd)

        return self.read_velocity(axis)

    """ STATE """

    def state(self, axis):
        self.trace("axis state")
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

        # the controller latches the previous error
        self.clear_error()

        axis = motion.axis
        _cmd = "MOV %s %g" % (axis.channel, motion.target_pos)
        self.send_no_ans(axis, _cmd)

        self.check_error(_cmd)

    def stop(self, axis):
        elog.debug("stop requested")
        self.send_no_ans(axis, "STP %s" % (axis.channel))

    """ COMMUNICATIONS"""

    def send(self, axis, cmd, timeout=None):
        _cmd = self._append_eoc(cmd)
        _ans = self.sock.write_readline(_cmd, timeout=timeout)
        _ans = self._remove_eoc(_ans)
        return _ans

    def clear_error(self):
        self._get_error()

    def check_error(self, cmd):
        # Check error code
        (_err_nb, _err_str) = self._get_error()
        if _err_nb != 0:
            _str = 'ERROR on cmd "%s": #%d(%s)' % (cmd, _err_nb, _err_str)
            # by default, an exception will be raised
            elog.error(_str)

    def send_no_ans(self, axis, cmd):
        _cmd = self._append_eoc(cmd)
        self.sock.write(_cmd)

    @object_method(types_info=("None", "None"))
    def raw_flush(self, axis):
        self.sock.flush()

    """ RAW COMMANDS """

    def raw_write(self, cmd):
        _cmd = self._append_eoc(cmd)
        self.sock.write(_cmd)

    def raw_write_read(self, cmd):
        _cmd = self._append_eoc(cmd)
        _ans = self.sock.write_readline(_cmd)

        # handle multiple lines answer
        _ans = _ans + "\n"
        try:
            while True:
                _ans = _ans + self.sock.raw_read(timeout=.1)
        except:
            pass

        _ans = self._remove_eoc(_ans)
        return _ans

    def raw_write_readlines(self, cmd, lines):
        _cmd = self._append_eoc(cmd)
        _ans = "\n".join(self.sock.write_readlines("%s\n" % _cmd, lines))
        _ans = self._remove_eoc(_ans)
        return _ans

    def _append_eoc(self, cmd):
        _cmd = cmd.strip()
        if not _cmd.endswith("\n"):
            _cmd = cmd + "\n"
        elog.debug(">>>> %s" % (_cmd.strip("\n")))
        return _cmd

    def _remove_eoc(self, ans):
        _ans = ans.strip().strip("\n\r")
        elog.debug("<<<< %s" % _ans)
        return _ans

    """
    E727 specific
    """

    @object_method(types_info=("None", "str"))
    def get_identifier(self, axis, timeout=None):
        return self.send(axis, "IDN?", timeout)

    def get_voltage(self, axis):
        """ Returns voltage read from controller."""
        _ans = self.send(axis, "SVA?")
        _voltage = float(_ans.split("=")[1])
        return _voltage

    def set_voltage(self, axis, new_voltage):
        """ Sets Voltage to the controller."""
        _cmd = "SVA %s %g" % (axis.channel, new_voltage)
        self.send_no_ans(axis, _cmd)
        self.check_error(_cmd)

    def _get_velocity(self, axis):
        """
        Returns velocity taken from controller.
        """
        _ans = self.send(axis, "VEL? %s" % (axis.channel))
        _velocity = float(_ans.split("=")[1])

        return _velocity

    def _get_pos(self, axis):
        """
        Returns real position read by capacitive sensor.
        """
        _ans = self.send(axis, "POS? %s" % (axis.channel))
        _pos = float(_ans.split("=")[1])
        return _pos

    """ ON TARGET """

    def _get_target_pos(self, axis):
        """
        Returns last target position (setpoint value).
        """
        _ans = self.send(axis, "MOV? %s" % (axis.channel))
        # _ans should looks like "1=-8.45709419e+01"
        _pos = float(_ans.split("=")[1])

        return _pos

    def _get_on_target_status(self, axis):
        _ans = self.send(axis, "ONT? %s" % (axis.channel))

        _status = _ans.split("=")[1]

        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            elog.error(
                "ERROR on _get_on_target_status, _ans=%r" % _ans, raise_exception=False
            )
            return -1

    """ CLOSED LOOP"""

    def _get_closed_loop_status(self, axis):
        _ans = self.send(axis, "SVO? %s" % (axis.channel))

        _status = _ans.split("=")[1]

        if _status == "1":
            return True
        elif _status == "0":
            return False
        else:
            elog.error(
                "ERROR on _get_closed_loop_status, _ans=%r" % _ans,
                raise_exception=False,
            )
            return -1

    def _set_closed_loop(self, axis, state):
        if state:
            _cmd = "SVO %s 1" % (axis.channel)
        else:
            _cmd = "SVO %s 0" % (axis.channel)
        self.send_no_ans(axis, _cmd)
        self.check_error(_cmd)

    @object_method(types_info=("None", "None"))
    def open_loop(self, axis):
        self._set_closed_loop(axis, False)

    @object_method(types_info=("None", "None"))
    def close_loop(self, axis):
        self._set_closed_loop(axis, True)

    def _get_error(self):
        # Does not use send() to be able to call _get_error in send().
        _error_number = int(self.raw_write_read("ERR?"))
        _error_str = pi_gcs.get_error_str(int(_error_number))

        return (_error_number, _error_str)

    def get_info(self, axis):
        """
        Returns a set of usefull information about controller.
        Helpful to tune the device.
        """
        _tab = 30

        (_err_nb, _err_str) = self._get_error()
        _txt = "%*s: %d (%s)\n" % (_tab, "Last Error", _err_nb, _err_str)

        # use command "HDA?" to get add parameters address + description
        _infos = [
            ("Identifier", "IDN?"),
            ("Com level", "CCL?"),
            ("Firmware developer", "SEP? 1 0xffff000f"),
            ("Firmware name", "SEP? 1 0xffff0007"),
            ("Firmware version", "SEP? 1 0xffff0008"),
            ("Firmware description", "SEP? 1 0xffff000d"),
            ("Firmware date", "SEP? 1 0xffff000e"),
            ("Firmware developer", "SEP? 1 0xffff000f"),
            ("Real Position", "POS? %s"),
            ("Setpoint Position", "MOV? %s"),
            ("On target", "ONT? %s"),
            ("Velocity", "VEL? %s"),
            ("Closed loop status", "SVO? %s"),
            ("Auto Zero Calibration ?", "ATZ? %s"),
            ("Analog input setpoint", "AOS? %s"),
            ("ADC value of analog input", "TAD? %s"),
            ("Analog setpoints", "TSP? %s"),
            ("AutoZero Low Voltage", "SPA? 1 0x07000A00"),
            ("AutoZero High Voltage", "SPA? 1 0x07000A01"),
            ("Range Limit min", "SPA? 1 0x07000000"),
            ("Range Limit max", "SPA? 1 0x07000001"),
            ("ON Target Tolerance", "SPA? 1 0x07000900"),
            ("Settling time", "SPA? 1 0X07000901"),
        ]

        for i in _infos:
            _cmd = i[1]
            if "%s" in _cmd:
                _cmd = _cmd % (axis.channel)
            _ans = self.send(axis, _cmd)
            _txt = _txt + "%*s: %s\n" % (_tab, i[0], _ans)
            self.check_error(_cmd)

        _txt = _txt + "%*s:\n%s\n" % (
            _tab,
            "Communication parameters",
            self.raw_write_read("IFC?"),
        )

        return _txt
