# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import time
import traceback
from bliss.controllers.motor import Controller
from bliss.comm.util import get_comm
from bliss.common.axis import AxisState
from bliss import global_map
from bliss.common.logtools import log_error, log_info, log_debug
from bliss.comm.util import SERIAL

"""
Bliss controller for ESRF ISG VSCANNER voltage scanner unit.
"""


class VSCANNER(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)
        self._status = "uninitialized"
        self.comm = None

    def initialize(self):
        """
        Open one socket for 2 channels.
        """
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        self.comm = get_comm(self.config.config_dict, SERIAL, timeout=1)

        global_map.register(self, children_list=[self.comm])

        self._status = "SERIAL communication configuration found"

        try:
            # _ans should be like : 'VSCANNER 01.02'
            _ans = self.comm.write_readline(b"?VER\r\n", eol="\r\n").decode()
            self._status += "\ncommunication ok "
        except OSError:
            _ans = "no ans"
            self._status = sys.exc_info()[1]
            log_error(self, self._status)
        except Exception:
            _ans = "no ans"
            self._status = (
                'communication error : cannot communicate with serial "%s"' % self.comm
            )
            log_error(self, self._status)
            traceback.print_exc()

        try:
            _ans.index("VSCANNER")
            self._status += (
                "VSCANNER found (substring VSCANNER found in answer to ?VER)."
            )
        except Exception:
            self._status = (
                'communication error : no VSCANNER found on serial "%s"' % self.comm
            )

        log_debug(self, self._status)

    def close(self):
        """
        Close the serial line.
        """
        self.comm.close()

    def initialize_axis(self, axis):
        """
        Init
        - fix possible wrong positions (<0V or >10V)
        """
        axis.chan_letter = axis.config.get("chan_letter")

        self.send_no_ans(axis, "NOECHO")

        ini_pos = self.read_position(axis)
        if ini_pos < 0:
            lprint(
                f"WARNING: reseting VSCANNER {axis.chan_letter}"
                f"negative position ({ini_pos}) to 0 !!"
            )
            _cmd = "V%s 0" % (axis.chan_letter)
            self.send_no_ans(axis, _cmd)

        if ini_pos > 10:
            lprint(
                f"WARNING: reseting VSCANNER {axis.chan_letter}"
                f"wrong position ({ini_pos}) to 10 !!"
            )
            _cmd = "V%s 10" % (axis.chan_letter)
            self.send_no_ans(axis, _cmd)

    def read_position(self, axis, last_read={"t": time.time(), "pos": [None, None]}):
        """
        Return position's setpoint of <axis> in controller units (Volts)
        * Booth axis setpoint positions are read simultaneously.
          the result is time-stamped and kept in cache.
        * values are in Volts; command used is "?VXY"

        Args:
            - <axis> : bliss axis.
            - [<measured>] : boolean : if True, function must
              return measured position.
        Return:
            - <position> : float : axis setpoint in Volts.
        """
        cache = last_read

        if time.time() - cache["t"] < 0.005:
            _pos = cache["pos"]
            log_debug(
                self, f"read_position() -- voltages in cache: {_pos[0]} {_pos[1]}"
            )
        else:
            _ans = self.send(axis, "?VXY")
            _pos = list(map(float, _ans.split(" ")))
            log_debug(
                self,
                f"read_position() -- voltages NOT in cache, re-read: {_pos[0]} {_pos[1]}",
            )

        if axis.chan_letter == "X":
            _pos = _pos[0]
        elif axis.chan_letter == "Y":
            _pos = _pos[1]
        else:
            raise ValueError("read_position() -- invalid chan letter")

        log_debug(self, f"read_position() -- V{axis.chan_letter}={_pos}")

        return _pos

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Return:
            - <velocity> (float): velocity in V/s
        """
        _ans = self.send(axis, "?VEL")
        # _ans should looks like: "0.2 0.1"
        # First field is velocity (in V/ms)
        # Second field is "line waiting" (hummmm second field is not always present ???)

        _float_ans = list(map(float, _ans.split(" ")))
        if len(_float_ans) == 1:
            _vel = _float_ans[0]
        elif len(_float_ans) == 2:
            (_vel, _line_waiting) = _float_ans
        else:
            log_error(self, f"Invalid  '?VEL' answer:{_float_ans} ")

        # VSCANNER answer is in V/ms
        # V/s = ( V/ms ) * 1000
        _velocity = _vel * 1000

        log_debug(self, "read_velocity() -- %g " % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        """
        Set velocity of <axis>, make the conversion in V/ms
        * <new_velocity> is in user_unit/s
        * 'VEL <_new_vel>': set velocity in V/ms
        """
        # Convert in V/ms
        _new_vel = new_velocity / 1000.0
        self.send_no_ans(axis, "VEL %f 0" % _new_vel)
        log_debug(self, "set_velocity() -- %g" % _new_vel)

    def state(self, axis):
        """
        Return the state of <axis>.
        return type is 'AxisState'.
        """
        _ans = self.send(axis, "?STATE")
        if _ans == "READY":
            return AxisState("READY")

        if _ans == "LWAITING":
            return AxisState("MOVING")

        if _ans == "LRUNNING":
            return AxisState("MOVING")

        if _ans == "PWAITING":
            return AxisState("MOVING")

        if _ans == "PRUNNING":
            return AxisState("MOVING")

        return AxisState("FAULT")

    def prepare_move(self, motion):
        """
        Prepare parameters for the move in controller.
        'prepare_move()' is called once per axis involved in the move.
        """
        # def prepare_move(self, motion, last_motion={"dVX": None, "dVY": None}):

        #  _msg =  f"prepare_move() -- {motion.axis.name}  target={motion.target_pos}"
        #  _msg += f" delta={motion.delta} backlash={motion.backlash}"
        #  log_debug(self, _msg)
        #
        #  motion_cache = last_motion
        #  log_debug(self, f" #########  motion_cache={motion_cache}")
        #
        #  if motion_cache["dVX"] or motion_cache["dVY"]:
        #      log_debug(self, f"This is the second axis prepare_move().")
        #      if motion.axis.chan_letter == "X":
        #          motion_cache["dVX"] = motion.delta
        #      if motion.axis.chan_letter == "Y":
        #          motion_cache["dVY"] = motion.delta
        #  else:
        #      log_debug(self, f"This is the first axis prepare_move() ... OR the only one ???.")
        #      if motion.axis.chan_letter == "X":
        #          motion_cache["dVX"] = motion.delta
        #      if motion.axis.chan_letter == "Y":
        #          motion_cache["dVY"] = motion.delt

        # In order to prepare the vscanner, we must know all the axes involved in motion.
        # but... how to know ?
        # So... do nothing  and do everything in start_all() :(

        pass

    def start_one(self, motion):
        """
        Start motion of one axis.
        In VSCANNER case, just delegate the work to start_all().
        """
        self.start_all(motion)

        # log_debug(self, "start_one() -- start_one() called")
        # _velocity = float(motion.axis.config.get("velocity"))
        # if _velocity == 0:
        #     log_debug(self, "start_one() -- immediate move")
        #     _cmd = "V%s %s" % (motion.axis.chan_letter, motion.target_pos)
        #     self.send_no_ans(motion.axis, _cmd)
        # else:
        #     # Start 1 scan.
        #     # pre-scan Voltages are saved by the controller and restored in case of abort.
        #     _cmd = "START 1 NORET"
        #     log_debug(self, "start_one() -- _cmd_START=%s" % _cmd)
        #     self.send_no_ans(motion.axis, _cmd)

    def start_all(self, *motion_list):
        """
        Start simultaneous axis movements on one controller.
        Called once per controller with all the axis to move.
        Return immediately.
        motions positions are in motor units.
        """
        motion_params = dict()
        velocities = list()

        first_axis = motion_list[0].axis

        for motion in motion_list:
            _msg = f"start_all() -- {motion.axis.name}  target={motion.target_pos}"
            _msg += f" delta={motion.delta} backlash={motion.backlash}"
            log_debug(self, _msg)

            # Store motions parameters in a dict to create the SCAN or VXY command.
            motion_params[motion.axis.chan_letter] = (motion.target_pos, motion.delta)

            # Crappy hack:
            # Store velocities in a list to determine if we do a SCAN or a VXY command.
            # NB: values are not used.
            velocities.append(float(motion.axis.velocity) * motion.axis.steps_per_unit)

            # Q: in which case there is no velocity in motion ???

        if any(velocities):
            _msg = f"start_all() -- SCAN (relative) move"
            log_debug(self, _msg)

            # first_axis.velocity is in user units.
            # ??? only the first axis ?
            self.set_velocity(
                first_axis, first_axis.velocity * first_axis.steps_per_unit
            )

            # LINE <dVx> <dVy> <nPixel> <lMode>
            # Initialize the line settings that are used by the PSHAPE
            #   command to fill the internal scan line table.
            # <dVx> <dVy> are the wanted displacement in Volts.
            try:
                dX = motion_params["X"][1]
            except KeyError:
                dX = 0

            try:
                dY = motion_params["Y"][1]
            except KeyError:
                dY = 0
            number_of_pixel = 1
            line_mode = "C"  # mode continuous (S for stepping)
            _cmd = f"LINE {dX} {dY} {number_of_pixel} {line_mode}"
            log_debug(self, f"prepare_move() -- _cmd_LINE='{_cmd}'")
            self.send_no_ans(first_axis, _cmd)

            # SCAN <dX> <dY> <nLine> <'U'nidirectional or 'B'i-directional>
            # Define relative spacing between lines of a scan: 0 0 in
            # our case to perform a single movement on the 2 axes.
            _cmd = "SCAN 0 0 1 U"
            log_debug(self, f"start_all() -- _cmd_SCAN='{_cmd}'")
            self.send_no_ans(first_axis, _cmd)

            # PSHAPE ALL: clean and generate the line table.
            _cmd = "PSHAPE ALL"
            log_debug(self, f"start_all() -- _cmd: '{_cmd}'")
            self.send_no_ans(first_axis, _cmd)

            # START
            _cmd = "START 1 NORET"
            log_debug(self, f"start_all() --_cmd_START={_cmd}")
            self.send_no_ans(first_axis, _cmd)

        else:
            _msg = f"start_all() -- VXY / instant (absolute) move"
            log_debug(self, _msg)
            try:
                targetX = motion_params["X"][0]
            except KeyError:
                targetX = 0

            try:
                targetY = motion_params["Y"][0]
            except KeyError:
                targetY = 0

            if len(motion_params) == 2:
                _cmd = f"VXY {targetX} {targetY}"
            elif len(motion_params) == 1 and motion_params[0][0] == "X":
                _cmd = f"VX {targetX}"
            elif len(motion_params) == 1 and motion_params[0][0] == "Y":
                _cmd = f"VY {targetY}"
            else:
                log_error(
                    self, f"start_all() -- motion problem... vtargets={motion_params} "
                )

            log_debug(self, f"start_all() -- move command : '{_cmd}'")
            self.send(first_axis, _cmd)

    def stop(self, axis):
        """
        Halt a scan (not a movement ?)
        If a scan is running, it is stopped and the output voltages
           are set back to the initial values.
        """
        self.send_no_ans(axis, "STOP")

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
        return self.comm.write_readline(cmd.encode(), eol="\r\n").decode()

    def raw_write_readlines(self, cmd, lines):
        """
        - Add '\r\n' terminator to <cmd> string
        - Send <cmd> string to the controller and read back <lines> lines
        - <cmd>: 'str'
        - <lines>: 'int'
        Return 'str'
        """
        _cmd = cmd.encode() + b"\r\n"

        # get a list of string.
        _ans = self.comm.write_readlines(_cmd, lines, eol="\r\n")
        _ans_lines = [line.decode() for line in _ans]
        return "\n".join(_ans_lines)

    def get_id(self, axis):
        """
        Return firmware version.
        """
        _ans = self.send(axis, "?VER")
        return _ans

    def get_error(self):
        """
        Print and return error string read on controller.
        If no error, VSCANNER return 'OK'.
        Do not use 'send()' to be usable in 'send()'.
        No 'axis' parameter: query directly the controller.
        """
        _ans = self.comm.write_readline(b"?ERR\r\n")
        if _ans != b"OK\r":
            log_error(self, f"VSCANNER ERROR: {_ans}\n")
        return _ans

    def get_info(self, axis=None):
        """
        Return a set of information about axis and controller.
        """
        info_str = ""
        info_str += "###############################\n"
        info_str += f"Config:\n"
        info_str += f"  url={self.config.config_dict['serial']['url']}\n"
        info_str += f"  class={self.config.config_dict['class']}\n"
        #        info_str += f"  channel letter:{axis.chan_letter}\n"
        info_str += "###############################\n"
        info_str += f"?ERR: {self.get_error()}\n"
        info_str += "###############################\n"
        info_str += f"'?INFO' command:\n"
        info_str += f"firmware version   : {self.get_version()}\n"
        info_str += f"output voltage     : {self.get_voltages()}\n"
        info_str += f"unit state         : {self.get_state()}\n"
        info_str += "###############################\n"
        info_str += self.raw_write_readlines("?INFO\r\n", 13)
        info_str += "\n"
        info_str += "###############################\n"

        return info_str

    def get_version(self):
        return self.raw_write_read("?VER\r\n")

    def get_voltages(self):
        return self.raw_write_read("?VXY\r\n")

    def get_state(self):
        return self.raw_write_read("?STATE\r\n")

    def __info__(self):
        """
        Return user info only.
        See get_info() for more detailed information.
        """
        info_str = "VSCANNER:\n"
        info_str += f"     ?ERR: {self.get_error().decode()}\n"
        info_str += f"     output voltage : {self.get_voltages()}\n"
        info_str += f"     state         : {self.get_state()}\n"
        info_str += self.comm.__info__()
        return info_str

    def send(self, axis, cmd):
        """
        - Send command <cmd> to the VSCANNER.
        - Type of <cmd> must be 'str'
        - Convert <cmd> into 'bytes'
        - Add the terminator characters : "\r\n"
        - Channel is defined in <cmd>.
        - <axis> is passed for debugging purposes.
        - Return answer from controller.

        Args:
            - <axis> : passed for debugging purposes.
            - <cmd> : command to send to controller (Channel is already mentionned  in <cmd>).

        Return:
            - 1-line answer received from the controller (without "\\\\n" terminator).

        Raise:
            ?
        """

        # Do not log communications ? we can activate debug on serial...
        # log_debug(self, "cmd=%r" % cmd)
        _cmd = cmd + "\r\n"
        self.comm.write(_cmd.encode())

        # _t0 = time.time()

        _ans = self.comm.readline(eol="\r\n").decode().rstrip()

        # TODO or not ?
        # _err = self.get_error()

        # log_debug(self, "ans=%s" % repr(_ans))
        # _duration = time.time() - _t0
        # print "    Sending: %r Receiving: %r  (duration : %g)" % (_cmd, _ans, _duration)
        return _ans

    def send_no_ans(self, axis, cmd):
        """
        - Send command <cmd> to the VSCANNER
        - Type of <cmd> must be 'str'
        - Add the 'newline' terminator character : "\r\n"
        - Convert <cmd> into 'bytes'
        - Channel is defined in <cmd>
        - <axis> is passed for debugging purposes
        - Used for answer-less commands, then return nothing
        """
        # log_debug(self, "send_no_ans : cmd=%r" % cmd)

        _cmd = cmd + "\r\n"
        self.comm.write(_cmd.encode())

        # TODO or not ?
        # _err = self.get_error()
