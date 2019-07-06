# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from warnings import warn
from bliss.controllers.motor import Controller
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from bliss.common import session
from bliss.common.logtools import *

MAX_VELOCITY = 400000
MIN_VELOCITY = 1
MAX_ACCELERATION = 400000
MIN_ACCELERATION = 1
MAX_DECELERATION = 400000
MIN_DECELERATION = 1
MAX_CREEP_SPEED = 1000
MIN_CREEP_SPEED = 1
"""
Bliss controller for McLennan PM600/PM1000 motor controller.

"""


class PM600(Controller):
    def initialize(self):
        try:
            self.sock = get_comm(self.config.config_dict, TCP)
        except ValueError:
            host = config.get("host")
            port = int(config.get("port"))
            warn(
                "'host' and 'port' keywords are deprecated. " "Use 'tcp' instead",
                DeprecationWarning,
            )
            comm_cfg = {"tcp": {"url": "{0}:{1}".format(host, port)}}
            self.sock = get_comm(comm_cfg)

        session.get_current().map.register(self, children_list=[self.sock])

        # read spurious 'd' character when connected
        self.sock.readline(eol="\r")

    def finalize(self):
        self.sock.close()

    # Initialize each axis.
    def initialize_axis(self, axis):
        axis.channel = axis.config.get("address")

        axis.kf = axis.config.get("Kf", int, default=0)
        axis.kp = axis.config.get("Kp", int, default=10)
        axis.ks = axis.config.get("Ks", int, default=0)
        axis.kv = axis.config.get("Kv", int, default=0)
        axis.kx = axis.config.get("Kx", int)
        axis.slewrate = axis.config.get("velocity", float, default=1000.0)
        axis.accel = axis.config.get("acceleration", float, default=2000.0)
        axis.decel = axis.config.get("deceleration", int, default=3000)
        axis.creep_speed = axis.config.get("creep_speed", int, default=800)
        axis.creep_steps = axis.config.get("creep_steps", int, default=0)
        axis.limit_decel = axis.config.get("limit_decel", int, default=2000000)
        axis.settling_time = axis.config.get("settling_time", int, default=100)
        axis.window = axis.config.get("window", int, default=4)
        axis.threshold = axis.config.get("threshold", int, default=50)
        axis.tracking = axis.config.get("tracking", int, default=4000)
        axis.timeout = axis.config.get("timeout", int, default=8000)
        axis.soft_limit_enable = axis.config.get("soft_limit_enable", int, default=1)
        axis.low_steps = axis.config.get("low_steps", float, default=-2000000000)
        axis.high_steps = axis.config.get("high_steps", float, default=2000000000)
        axis.gearbox_ratio_numerator = axis.config.get(
            "gearbox_ratio_numerator", int, default=1
        )
        axis.gearbox_ratio_denominator = axis.config.get(
            "gearbox_ratio_denominator", int, default=1
        )
        axis.encoder_ratio_numerator = axis.config.get(
            "encoder_ratio_numerator", int, default=1
        )
        axis.encoder_ratio_denominator = axis.config.get(
            "encoder_ratio_denominator", int, default=1
        )
        """
        # Set velocity feedforward on axis
        self.io_command("KF", axis.channel, axis.kf)
        # Set the proportional gain on axis
        self.io_command("KP", axis.channel, axis.kp)
        # Set the Sum gain on axis
        self.io_command("KS", axis.channel, axis.ks)
        # Set the Velocity feedback on axis
        self.io_command("KV", axis.channel, axis.kv)
        # Set the Extra Velocity feedback on axis
        self.io_command("KX", axis.channel, axis.kx)
        """
        # Set slew rate of axis (steps/sec)
        self.io_command("SV", axis.channel, int(axis.slewrate))
        # Set acceleration of axis (steps/sec/sec)
        self.io_command("SA", axis.channel, int(axis.accel))
        # Set deceleration of axis (steps/sec/sec)
        self.io_command("SD", axis.channel, axis.decel)
        # Set creep speed of axis (steps/sec/sec)
        self.io_command("SC", axis.channel, axis.creep_speed)
        # Set number of creep steps at the end of a move (steps)
        self.io_command("CR", axis.channel, axis.creep_steps)
        # Set the deceleration rate for stopping when hitting a Hard Limit or a Soft Limit
        self.io_command("LD", axis.channel, axis.limit_decel)
        # Set settling time (milliseconds)
        self.io_command("SE", axis.channel, axis.settling_time)
        # Set the Set the Window for axis (steps)
        self.io_command("WI", axis.channel, axis.window)
        # Set the threshold before motor stalled condition (%)
        self.io_command("TH", axis.channel, axis.threshold)
        # Set the tracking window of the axis (steps)
        self.io_command("TR", axis.channel, axis.tracking)
        # Set the axis time out (millisecond)
        self.io_command("TO", axis.channel, axis.timeout)
        # Sets the soft limits (enable = 1, disable = 0)
        self.io_command("SL", axis.channel, axis.soft_limit_enable)
        if axis.soft_limit_enable == 1:
            # Set the axis upper soft limit position (steps)
            self.io_command("UL", axis.channel, axis.high_steps)
            # Set the axis lower soft limit position (steps)
            self.io_command("LL", axis.channel, axis.low_steps)
        # Set encoder ratio
        cmd = "ER{0}/{1}".format(
            axis.encoder_ratio_numerator, axis.encoder_ratio_denominator
        )
        self.io_command(cmd, axis.channel)
        # Set gearbox ratio numerator
        self.io_command("GN", axis.channel, axis.gearbox_ratio_numerator)
        # Set gearbox ratio denominator
        self.io_command("GD", axis.channel, axis.gearbox_ratio_denominator)

    def finalize_axis(self):
        pass

    def initialize_encoder(self, encoder):
        encoder.channel = encoder.config.get("address")

    def read_position(self, axis):
        reply = self.io_command("OC", axis.channel)
        return float(reply)

    def read_encoder(self, encoder):
        return float(self.io_command("OA", encoder.channel))

    def read_acceleration(self, axis):
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        return float(tokens[8])

    def read_deceleration(self, axis):
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        return int(tokens[11])

    def read_velocity(self, axis):
        reply = self.io_command("QS", axis.channel)
        return float(reply.split()[5])

    def read_firstvelocity(self, axis):
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        return int(tokens[2])

    def set_velocity(self, axis, velocity):
        if velocity > MAX_VELOCITY or velocity < MIN_VELOCITY:
            log_error(self, "PM600 Error: velocity out of range")
        reply = self.io_command("SV", axis.channel, velocity)
        if reply != "OK":
            log_error(self, "PM600 Error: Unexpected response to set_velocity" + reply)

    def set_firstvelocity(self, axis, creep_speed):
        if creep_speed > MAX_CREEP_SPEED or velocity < MIN_CREEP_SPEED:
            log_error(self, "PM600 Error: creep_speed out of range")
        reply = self.io_command("SC", axis.channel, creep_speed)
        if reply != "OK":
            log_error(
                self, "PM600 Error: Unexpected response to set_firstvelocity" + reply
            )

    def set_acceleration(self, axis, acceleration):
        if acceleration > MAX_ACCELERATION or acceleration < MIN_ACCELERATION:
            log_error(self, "PM600 Error: acceleration out of range")
        reply = self.io_command("SA", axis.channel, acceleration)
        if reply != "OK":
            log_error(
                self, "PM600 Error: Unexpected response to set_acceleration" + reply
            )

    def set_decel(self, axis, deceleration):
        if deceleration > MAX_DECELERATION or deceleration < MIN_DECELERATION:
            log_error(self, "PM600 Error: deceleration out of range")
        reply = self.io_command("SD", axis.channel, deceleration)
        if reply != "OK":
            log_error(
                self, "PM600 Error: Unexpected response to set_deceleration" + reply
            )

    def set_position(self, axis, position):
        reply = self.io_command("AP", axis.channel, position)
        if reply != "OK":
            log_error(self, "PM600 Error: Unexpected response to set_position" + reply)

    def state(self, axis):
        """
        Return interpretation of status 
        """
        status = self.status(axis)
        if status[1:2] == "1" or (status[2:3] == "1" and status[3:4] == "1"):
            return AxisState("FAULT")
        if status[2:3] == "1":
            return AxisState("LIMPOS")
        if status[3:4] == "1":
            return AxisState("LIMNEG")
        if status[0:1] == "0":
            return AxisState("MOVING")
        else:
            return AxisState("READY")

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        reply = self.io_command("MA", motion.axis.channel, motion.target_pos)
        if reply != "OK":
            log_error(self, "PM600 Error: Unexpected response to move absolute" + reply)

    def stop(self, motion):
        reply = self.io_command("ST", motion.axis.channel)
        if reply != "OK":
            log_error(self, "PM600 Error: Unexpected response to stop" + reply)

    def start_all(self, *motion_list):
        for motion in motion_list:
            self.start_one(motion)

    def stop_all(self, *motion_list):
        for motion in motion_list:
            self.stop(motion)

    def home_search(self, axis, switch):
        reply = self.io_command("DM00100000", axis.channel)
        if reply != "OK":
            log_error(self, "PM600 Error: Unexpected response to datum mode" + reply)
        reply = self.io_command("HD", axis.channel, (+1 if switch > 0 else -1))
        if reply != "OK":
            log_error(self, "PM600 Error: Unexpected response to home to datum" + reply)

    def home_state(self, axis):
        return self.state(axis)

    def get_info(self, axis):
        nlines = 23
        cmd = axis.channel + "QA\r"
        reply_list = self.sock.write_readlines(
            cmd.encode(), nlines, eol="\r\n", timeout=5
        )
        # Strip the echoed command from the first reply
        first_line = reply_list[0].decode()
        idx = first_line.find("\r")
        if idx == -1:
            log_error(self, "PM600 Error: No echoed command")
        answer = first_line[idx + 1 :]
        for i in range(1, nlines):
            answer = answer + "\n" + reply_list[i].decode()
        return answer

    def io_command(self, command, channel, value=None):
        if value:
            cmd = channel + command + str(value) + "\r"
        else:
            cmd = channel + command + "\r"

        ans = self.sock.write_readline(cmd.encode(), eol=b"\r\n")
        reply = ans.decode()
        # The response from the PM600 is terminated with CR/LF.  Remove these
        newreply = reply.rstrip("\r\n")
        # The PM600 always echoes the command sent to it, before sending the response.  It is terminated
        # with a carriage return.  So we need to delete all characters up to and including the first
        # carriage return
        idx = newreply.find("\r")
        if idx == -1:
            log_error(self, "PM600 Error: No echoed command")
        answer = newreply[idx + 1 :]
        # check for the error character !
        idx = answer.find("!")
        if idx != -1:
            log_error(self, "PM600 Error: " + answer[idx:])
            return
        # Now remove the channel from the reply and check against the requested channel
        idx = answer.find(":")
        replied_channel = int(answer[:idx])
        if int(channel) != replied_channel:
            log_error(self, f"PM600 Error: Wrong channel replied [{replied_channel}]")
        return answer[idx + 1 :]

    def raw_write_read(self, command):
        reply = self.sock.write_readline(command.encode(), eol="\r\n")
        return reply.decode()

    def raw_write(self, command):
        self.sock.write(command.encode())

    """
    PM600 added commands
    """

    @object_method(types_info=("None", "str"))
    def status(self, axis):
        """ 
        Return raw status string 

        status = "abcdefgh" where:
        a is 0 = Busy or 1 = Idle
        b is 0 = OK   or 1 = Error (abort, tracking, stall, timeout etc.)
        c is 0 = Upper hard limit is OFF or 1 = Upper hard limit is ON
        d is 0 = Lower hard limit is OFF or 1 = Lower hard limit is ON
        e is 0 = Not jogging or joystick moving or 1 = Jogging or joystick moving
        f is 0 = Not at datum sensor point or 1 = On datum sensor point
        g is 0 = Future use or 1 = Future use
        h is 0 = Future use or 1 = Future use
        """
        return self.io_command("OS", axis.channel)

    @object_method(types_info=("None", "int"))
    def get_id(self, axis):
        """
        This command is used to give the type of controller
        and its internal software revision.
        """
        return self.io_command("ID", axis.channel)

    @object_method(types_info=("None", "None"))
    def abort(self, axis):
        """
        The control of the motor is aborted.
        A user abort may be reset with the 'reset' command
        """
        self.io_command("AB", axis.channel)

    @object_method(types_info=("None", "None"))
    def reset(self, axis):
        """ 
        This command will reset the tracking abort, stall abort,
        time out abort or user(command) abort conditions and
        re-enable the servo control loop. It will also set the
        Command position to be equal to the Actual position
        """
        self.io_command("RS", axis.channel)

    @object_method(types_info=("None", "float"))
    def get_deceleration(self, axis):
        return self.read_deceleration(axis)

    @object_method(types_info=("float", "None"))
    def set_deceleration(self, axis, deceleration):
        return self.set_decel(axis, deceleration)
