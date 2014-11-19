from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING

import pi_gcs
from bliss.comm import tcp

import sys
import time

"""
Bliss controller for ethernet PI E753 piezo controller.
Cyril Guilloud ESRF BLISS January 2014
"""


class PI_E753(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self.host = self.config.get("host")

    def __del__(self):
        print "PI_E753 DESTRUCTORRRRRR******+++++++++++++++++++++++++++++++++"

    # Init of controller.
    def initialize(self):
        elog.debug("initialization")
        elog.info("initialization")

        self.sock = tcp.Socket(self.host, 50000)

    def finalize(self):
        print "PI_E753 controller finalization**********************************"
        # not called at end of device server ??? :(
        # called on a new axis creation ???

        if self.sock:
            self.sock.close()

    # Init of each axis.
    def initialize_axis(self, axis):
        elog.debug("axis initialization")

        # Enables the closed-loop.
        self.sock.write("SVO 1 1\n")

    def read_position(self, axis, measured=False):
        if measured:
            _ans = self._get_pos()
            elog.debug("read_position measured = %f" % _ans)
        else:
            _ans = self._get_target_pos()
            elog.debug("read_position = %f" % _ans)

        return _ans

    def read_velocity(self, axis):
        return self._get_velocity(axis)

    def set_velocity(self, axis, new_velocity):
        elog.debug("set_velocity new_velocity = %f" % new_velocity)
        self.sock.write("VEL 1 %f\n" % new_velocity)
        return self.read_velocity(axis)

    def state(self, axis):
        if self._get_closed_loop_status():
            if self._get_on_target_status():
                return READY
            else:
                return MOVING
        else:
            raise RuntimeError("closed loop disabled")

    def prepare_move(self, motion):
        self._target_pos = motion.target_pos

    def start_one(self, motion):
        elog.debug("start_one target_pos = %f" % self._target_pos)
        self.sock.write("MOV 1 %g\n" % self._target_pos)

    def stop(self, axis):
        # to check : copy of current position into target position ???
        self.sock.write("STP\n")

    def raw_write(self, axis, com):
        self.sock.write("%s\n" % com)

    def raw_write_read(self, axis, com):
        return self.sock.write_read("%s\n" % com)

    """
    E753 specific communication
    """

    def _get_velocity(self, axis):
        """
        Returns velocity taken from controller.
        """
        _ans = self.sock.write_readline("VEL?\n")
        _velocity = float(_ans[2:])

        return _velocity

    def _get_pos(self):
        """
        Returns real position read by capcitive captor.
        """
        _ans = self.sock.write_readline("POS?\n")

        # _ans should looks like "1=-8.45709419e+01\n"
        # "\n" removed by tcp lib.
        _pos = float(_ans[2:])

        return _pos

    def _get_target_pos(self):
        """
        Returns last target position (setpoint value).
        """
        _ans = self.sock.write_readline("MOV?\n")

        # _ans should looks like "1=-8.45709419e+01\n"
        # "\n" removed by tcp lib.
        _pos = float(_ans[2:])

        return _pos

    def _get_identifier(self):
        return self.sock.write_readline("IDN?\n")

    def _get_closed_loop_status(self):
        _ans = self.sock.write_readline("SVO?\n")

        if _ans == "1=1":
            return True
        elif _ans == "1=0":
            return False
        else:
            return -1

    def _get_on_target_status(self):
        _ans = self.sock.write_readline("ONT?\n")

        if _ans == "":
            return True
        elif _ans == "":
            return False
        else:
            return -1

    def _get_error(self):
        _error_number = self.sock.write_readline("ERR?\n")
        _error_str = pi_gcs.get_error_str(_error_number)

        return (_error_number, _error_str)

    def _stop(self):
        self.sock.write("STP\n")

    def _test_melange(self, sleep_time=0.1):
        ii = 0
        _vel0 = self.sock.write_readline("VEL?\n")
        _ans_pos0 = self.sock.write_readline("POS?\n")[2:]
        _pos0 = int(round(float(_ans_pos0), 2))
        while True:
            time.sleep(sleep_time)
            sys.stdout.write(".")
            _vel = self.sock.write_readline("VEL?\n")
            _ans_pos = self.sock.write_readline("POS?\n")[2:]
            _pos = int(round(float(_ans_pos), 2))
            if _vel != _vel0:
                print "%d VEL = %s " % (ii, _vel)
            if abs(_pos - _pos0) > 1:
                print "%d POS = %s" % (ii, _ans_pos)
            ii = ii + 1

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
        _infos = [
            ("Identifier                 ", "IDN?\n"),
            ("Com level                  ", "CCL?\n"),
            ("Real Position              ", "POS?\n"),
            ("Setpoint Position          ", "MOV?\n"),
            ("Position low limit         ", "SPA? 1 0x07000000\n"),
            ("Position High limit        ", "SPA? 1 0x07000001\n"),
            ("Velocity                   ", "VEL?\n"),
            ("On target                  ", "ONT?\n"),
            ("Target tolerance           ", "SPA? 1 0X07000900\n"),
            ("Settling time              ", "SPA? 1 0X07000901\n"),
            ("Sensor Offset              ", "SPA? 1 0x02000200\n"),
            ("Sensor Gain                ", "SPA? 1 0x02000300\n"),
            ("Motion status              ", "#5\n"),
            ("Closed loop status         ", "SVO?\n"),
            ("Auto Zero Calibration ?    ", "ATZ?\n"),
            ("Analog input setpoint      ", "AOS?\n"),
            ("Low    Voltage Limit       ", "SPA? 1 0x07000A00\n"),
            ("High Voltage Limit         ", "SPA? 1 0x07000A01\n")
        ]

        _txt = ""

        for i in _infos:
            _txt = _txt + "        %s %s\n" % \
                (i[0], self.sock.write_readline(i[1]))

        _txt = _txt + "        %s    \n%s\n" %  \
            ("Communication parameters",
             "\n".join(self.sock.write_readlines("IFC?\n", 5)))

        _txt = _txt + "        %s    \n%s\n" %  \
            ("Analog setpoints",
             "\n".join(self.sock.write_readlines("TSP?\n", 2)))

        _txt = _txt + "        %s    \n%s\n" %   \
            ("ADC value of analog input",
             "\n".join(self.sock.write_readlines("TAD?\n", 2)))

# ###  TAD[1]==131071  => broken cable ??
# 131071 = pow(2,17)-1

        return _txt
