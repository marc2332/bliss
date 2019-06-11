# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from bliss.common import session

"""
- Bliss controller for PiezoMotor PMD206 piezo motor controller.
- Ethernet
- Cyril Guilloud ESRF BLISS
- Thu 10 Apr 2014 09:18:51
"""


def int_to_hex(dec_val):
    """
    Conversion function to code PMD206 messages.
    - ex : hex(1050)[2:] = "41a"
    - ex : hex(-3 + pow(2, 32))[2:] = "fffffffd"
    """
    if dec_val < 0:
        return hex(dec_val + pow(2, 32))[2:]
    else:
        return hex(dec_val)[2:]


def hex_to_int(hex_val):
    """
    Conversion function to decode PMD206 messages.
    - ex : int("41a", 16)- pow(2, 32) = 1050
    - ex : int("ffffffff", 16)  - pow(2, 32)  = -1
    """
    if int(hex_val, 16) > pow(2, 31):
        return int(hex_val, 16) - pow(2, 32)
    else:
        return int(hex_val, 16)


class PMD206(Controller):

    """
    - Bliss controller for PiezoMotor PMD206 piezo motor controller.
    - Ethernet
    - Cyril Guilloud ESRF BLISS
    - Thu 10 Apr 2014 09:18:51
    """

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._controller_error_codes = [
            (0x8000, "Abnormal reset detected."),
            (
                0x4000,
                "ComPic cannot communicate internally with MotorPic1 or MotorPic2",
            ),
            (0x2000, "MotorPic2 has sent an unexpected response (internal error)"),
            (0x1000, "MotorPic1 has sent an unexpected response (internal error)"),
            (0x800, "Error reading ADC. A voltage could not be read"),
            (0x400, "48V level low or high current draw detected"),
            (0x200, "5V level on driver board outside limits"),
            (0x100, "3V3 level on driver board outside limits"),
            (0x80, "Sensor board communication error detected"),
            (0x40, "Parity or frame error RS422 sensor UART. Check cable/termination"),
            (0x20, "Wrong data format on external sensor (RS422 or TCP/IP)"),
            (0x10, "External sensor not detected (RS422 and TCP/IP)"),
            (0x08, "Problem with UART on host. Check cable and termination"),
            (0x04, "Host command error - driver board (e.g. buffer overrun)"),
            (0x02, "300 ms command timeout ocurred"),
            (0x01, "Command execution gave a warning"),
        ]

        self._motor_error_codes = [
            (0x80, "48V low or other critical error, motor is stopped"),
            (0x40, "Temperature limit reached, motor is stopped"),
            (0x20, "Motor is parked"),
            (
                0x10,
                "Max or min encoder limit was reached in target mode, \
            or motor was stopped due to external limit signal ",
            ),
            (0x8, "Target mode is active"),
            (
                0x4,
                "Target position was reached (if target mode is active). \
            Also set during parking/unparking. ",
            ),
            (0x2, "Motor direction"),
            (0x1, "Motor is running"),
        ]

    def initialize(self):
        """
        Opens a single communication socket to the controller for all 1..6 axes.
        """
        try:
            self.sock = get_comm(self.config.config_dict, TCP, port=9760)
        except ValueError:
            host = self.config.get("host")
            warn("'host' keyword is deprecated. Use 'tcp' instead", DeprecationWarning)
            if not host.startswith("command://"):
                host = "command://" + host
            comm_cfg = {"tcp": {"url": host}}
            self.sock = get_comm(comm_cfg, port=9760)

        session.get_current().map.register(self, children_list=[self.sock])

        self._logger.debug("socket open : %r" % self.sock)

    def finalize(self):
        """
        Closes the controller socket.
        """
        self.sock.close()
        self._logger.debug("socket closed: %r" % self.sock)

    def initialize_axis(self, axis):
        axis.channel = axis.config.get("channel", int)

        # Stores one axis to talk to the controller.
        if axis.channel == 1:
            self.ctrl_axis = axis
            self._logger.debug("AX CH =%r" % axis.channel)

    def initialize_encoder(self, encoder):
        encoder.channel = encoder.config.get("channel", int)

    def set_on(self, axis):
        pass

    def set_off(self, axis):
        pass

    def read_position(self, axis):
        """
        Returns position's setpoint (in encoder counts).

        Args:
            - <axis> : bliss axis.
        Returns:
            - <position> : float :
        """
        #                      1234567812345678
        # example of answer : 'PM11MP?:fffffff6'
        _ans = self.send(axis, "TP?")
        _pos = hex_to_int(_ans[8:])
        self._logger.debug(
            "PMD206 position setpoint (encoder counts) read : %d (_ans=%s)"
            % (_pos, _ans)
        )

        return _pos

    def read_encoder(self, encoder):

        _ans = self.send(encoder, "MP?")
        _pos = hex_to_int(_ans[8:])
        self._logger.debug(
            "PMD206 position measured (encoder counts) read : %d (_ans=%s)"
            % (_pos, _ans)
        )

        return _pos

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float : velocity in motor-units
        """
        _velocity = 1

        self._logger.debug("read_velocity : %d" % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units. (encoder steps)
        Returns velocity in motor units.
        """
        _nv = new_velocity
        self._logger.debug("velocity NOT wrotten : %d " % _nv)

        return self.read_velocity(axis)

    def read_acctime(self, axis):
        """
        Returns acceleration time in seconds.
        """
        # _ans = self.send(axis, "CP?9")
        #                           123456789
        # _ans should looks like : 'PM11CP?9:00000030'
        # Removes 9 firsts characters.
        # _acceleration = hex_to_int(_ans[9:])

        return float(axis.settings.get("acctime"))

    def set_acctime(self, axis, new_acctime):
        # !!!! must be converted  ?
        # _nacc = int_to_hex(new_acctime)
        # _nacc = 30
        # self.send(axis, "CP=9,%d" % _nacc)

        axis.settings.set("acctime", new_acctime)
        return new_acctime

    def get_id(self, axis):
        # example of answer : "PM11XV?:13,10,10,070707,206,0004a35a1d42,01"
        # ----> Com V.13 ; pic1 V.10 ; pic2 V.10 ; sensor V.070707 ;
        #       driver.type 206 ; MAC:0004a35a1d42 ; IPmode:01

        _ans = self.send(axis, "XV?")
        _fields = _ans.split(":")[1].split(",")

        _msg = (
            "PiezoMotor PMD%s : Com V.%s ; pic1 V.%s ; pic2 V.%s ; sensor V.%s ; MAC:%s ; IPmode:%s"
            % (
                _fields[4],
                _fields[0],
                _fields[1],
                _fields[2],
                _fields[3],
                _fields[5],
                _fields[6],
            )
        )

        return _msg

    """
    STATUS
    """

    def pmd206_get_status(self, axis):
        """
        Sends status command (CS?) and puts results (hexa strings) in :
        - self._ctrl_status
        - self._axes_status[1..6]
        Must be called before get_controller_status and get_motor_status.
        """
        # broadcast command -> returns status of all 6 axis
        # _ans should looks like : 'PM11CS?:0100,20,20,20,20,20,20'

        # ~ 1.6ms
        _ans = self.send(axis, "CS?")

        self._axes_status = dict()

        (
            self._ctrl_status,
            self._axes_status[1],
            self._axes_status[2],
            self._axes_status[3],
            self._axes_status[4],
            self._axes_status[5],
            self._axes_status[6],
        ) = _ans.split(":")[1].split(",")

        self._logger.debug("ctrl status : %s" % self._ctrl_status)
        self._logger.debug("mot1 status : %s" % self._axes_status[1])
        self._logger.debug("mot2 status : %s" % self._axes_status[2])
        self._logger.debug("mot3 status : %s" % self._axes_status[3])
        self._logger.debug("mot4 status : %s" % self._axes_status[4])
        self._logger.debug("mot5 status : %s" % self._axes_status[5])
        self._logger.debug("mot6 status : %s" % self._axes_status[6])

    def get_controller_status(self):
        """
        Returns a string build with all status of controller.
        """
        _s = hex_to_int(self._ctrl_status)
        _status = ""

        for _c in self._controller_error_codes:
            if _s & _c[0]:
                # print _c[1]
                _status = _status + (_c[1] + "\n")

        return _status

    def get_motor_status(self, axis):
        """
        Returns a string build with all status of motor <axis>.
        """
        _s = hex_to_int(self._axes_status[axis.channel])
        _status = ""

        for _c in self._motor_error_codes:
            if _s & _c[0]:
                # print _c[1]
                _status = _status + (_c[1] + "\n")

        return _status

    def motor_state(self, axis):
        _s = hex_to_int(self._axes_status[axis.channel])

        self._logger.debug(
            "axis %d status : %s" % (axis.channel, self._axes_status[axis.channel])
        )

        if self.s_is_parked(_s):
            return AxisState("OFF")

        # running means position is corrected, related to closed loop
        # we just check if target position was reached
        if self.s_is_closed_loop(_s):
            if self.s_is_position_reached(_s):
                return AxisState("READY")
            else:
                return AxisState("MOVING")
        else:
            if self.s_is_moving(_s):
                return AxisState("MOVING")
            else:
                return AxisState("READY")

    def s_is_moving(self, status):
        return status & 0x1

    def s_is_closed_loop(self, status):
        return status & 0x08

    def s_is_position_reached(self, status):
        return status & 0x04

    def s_is_parked(self, status):
        return status & 0x20

    def state(self, axis):
        """
        Read status from controller.
        No way to read only single axis.
        """
        self.pmd206_get_status(axis)

        return self.motor_state(axis)

    def status(self, axis):
        """
        Returns a string composed by controller and motor status string.
        """
        return self.get_controller_status() + "\n\n" + self.get_motor_status(axis)

    """
    Movements
    """

    def prepare_move(self, motion):
        """
        - TODO for multiple move...
        """
        pass

    def start_one(self, motion):
        """
        - Sends

        Args:
            - <motion> : Bliss motion object.

        Returns:
            - None
        """

        # unpark only on demand !

        #        # unpark the axis motor if needed
        #        # status bit 0x20 : "Motor is parked"
        #        self.pmd206_get_status(motion.axis)
        #        _hex_status_string = self._axes_status[motion.axis.channel]
        #        _status = hex_to_int(_hex_status_string)
        #        if _status & 0x20:
        #            self._logger.info("Motor is parked. I unpark it")
        #            self.unpark_motor(motion.axis)

        # print "targetpos=", motion.target_pos
        _enc_target = int_to_hex(int(motion.target_pos))
        # print "_enc_target=", _enc_target
        self.send(motion.axis, "TP=%s" % _enc_target)

    def stop(self, axis):
        """
        Stops all axis motions sending CS=0 command.

        Args:
            - <axis> : Bliss axis object.
        """
        self.send(axis, "CS=0")

    """
    PMD206 specific communication
    """

    def send(self, axis, cmd):
        """
        - Adds 'CP<x><y>' prefix
        - Adds the 'carriage return' terminator character : "\\\\r"
        - Sends command <cmd> to the PMD206 controller.
        - Channel is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - if <axis> is 0 : sends a broadcast message.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : command to send to controller (Channel is already mentionned  in <cmd>).

        Returns:
            - Answer from controller for get commands.
            - True if for successful set commands.

        Raises:
            ?
        """
        # PC: don't know how to send a broadcast command to controller, not axis
        # intercept it here ...
        # put 0 instead of channel
        self._logger.debug("in send(%r)" % cmd)
        broadcast_command = cmd[:4] in ["CC=4", "CC=5"]
        if broadcast_command:
            self._logger.debug("BROADCAST COMMAND ")
            _prefix = "PM%d%d" % (1, 0)
        else:
            _prefix = "PM%d%d" % (1, axis.channel)

        _cmd = _prefix + cmd + "\r"
        _t0 = time.time()
        _ans = self.sock.write_readline(_cmd, eol="\r")
        self._logger.debug("send(%s) returns : %s " % (_cmd, _ans))

        set_command = cmd[:3] in ["DR=", "CS=", "TP=", "TR=", "RS="]

        if set_command:
            self._logger.debug("SET COMMAND ")
            if _ans != _cmd:
                pass
                # print "oh oh set command not answered correctly ?"
                # print "_ans=" ,_ans

        _duration = time.time() - _t0
        if _duration > 0.006:
            print(
                "PMD206 Received %s from Send %s (duration : %g ms) "
                % (repr(_ans), repr(_cmd), _duration * 1000)
            )

        return _ans

    def get_error(self, axis):
        pass

    def do_homing(self, axis, freq, max_steps, max_counts, first_dir):
        """
        Sends 'HO' command.
        """
        self.send(
            "HO=%d,%d,%d,%d,%d,%d"
            % (freq, max_steps, max_counts, first_dir, max_steps, max_counts)
        )

    def homing_sequence_status_string(self, status):
        _home_status_table = [
            ("0c", "initiating"),
            ("0b", "starting index mode 3"),
            ("0a", "starting direction 1"),
            ("09", "running direction 1"),
            ("08", "starting direction 2"),
            ("07", "running direction 2"),
            ("06", "is encoder counting ?"),
            ("05", "running direction 2"),
            ("04", "end direction 2"),
            ("03", "stopped with error"),
            ("02", "index not found"),
            ("01", "index was found"),
            ("00", "not started"),
        ]
        print(_home_status_table)

    @object_method(types_info=("None", "None"))
    def park_motor(self, axis):
        """
        Parks axis motor.
        """
        self.send(axis, "CC=1")

    @object_method(types_info=("None", "None"))
    def unpark_motor(self, axis):
        """
        Unpark axis motor (mandatory before moving).
        """
        self.send(axis, "CC=0")

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
            ("Firmware version               ", "SV?"),
            ("Extended Version Information   ", "XV?"),
            ("Controller status              ", "CS?"),
            ("Extended Controller status     ", "XS?"),
            ("Closed loop status             ", "CM?"),
            ("Mot. Pos. Encoder Value (hex)  ", "MP?"),
            ("Last target Position (hex)     ", "TP?"),
            ("Status of Homing Sequence      ", "HO?"),
            ("Cycle counter                  ", "CP?0"),
            ("Parking and initialization     ", "CP?1"),
            ("External limits                ", "CP?2"),
            ("Position limit high            ", "CP?3"),
            ("Position limit low             ", "CP?4"),
            ("Stop range (dead band)         ", "CP?5"),
            ("Encoder direction              ", "CP?6"),
            ("Minimum speed in target mode   ", "CP?7"),
            ("Maximum speed in target mode   ", "CP?8"),
            ("Speed ramp up in target mode   ", "CP?9"),
            ("Speed ramp down in target mode ", "CP?a"),
            ("StepsPerCount                  ", "CP?b"),
            ("Driver board temperature       ", "CP?10"),
            ("Driver board 48 V level        ", "CP?12"),
            ("Position                       ", "CP?14"),
            ("Wfm point and voltages         ", "CP?1d"),
            ("Target mode parameters         ", "CP?1e"),
        ]

        _txt = ""

        self.pmd206_get_status(axis)
        _ctrl_status = self.get_controller_status()
        _axis_status = self.get_motor_status(axis)

        for i in _infos:
            _txt = _txt + "    %s %s\n" % (i[0], self.send(axis, i[1]))
        _txt = _txt + "    ctrl status : %s" % _ctrl_status
        _txt = _txt + "    axis status : %s" % _axis_status
        _txt = _txt + "     IP address : %s" % self.get_ip(axis)

        return _txt

    def get_ip(self, axis):
        """
        Returns IP address as a 4 decimal numbers string.
        """
        _ans = self.send(axis, "IP?")
        return ".".join(
            map(str, list(map(hex_to_int, _ans.split(":")[1].split(",")[0:4])))
        )

    def raw_write(self, cmd):
        self._logger.info("no send_no_ans with PMD206")
        pass

    def raw_write_read(self, cmd):
        return self.send(self.ctrl_axis, cmd)

    @object_method(types_info=("str", "str"))
    def raw_write_read_axis(self, axis, cmd):
        return self.send(axis, cmd)
