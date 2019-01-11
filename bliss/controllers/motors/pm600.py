# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from warnings import warn

from bliss.controllers.motor import Controller
from bliss.common import log as log
from bliss.common.utils import object_method
from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from distutils.log import Log

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
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        log.level(10)

    def initialize(self):
        log.debug("initialize() called")
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

        log.info("initialize() create socket %s" % str(self.sock))
        # read spurious 'd' character when connected
        self.sock.readline(eol="\r")

    def finalize(self):
        log.debug("finalize() called")
        self.sock.close()

    # Initialize each axis.
    def initialize_axis(self, axis):
        log.debug("initialize_axis() called")
        axis.channel = axis.config.get("address")

        axis.kf = axis.config.get("Kf", int, default=0)
        axis.kp = axis.config.get("Kp", int, default=10)
        axis.ks = axis.config.get("Ks", int, default=0)
        axis.kv = axis.config.get("Kv", int, default=0)
        axis.kx = axis.config.get("Kx", int)
        axis.slewrate = axis.config.get("velocity", int, default=1000)
        axis.accel = axis.config.get("acceleration", int, default=2000)
        axis.decel = axis.config.get("deceleration", int, default=3000)
        axis.creep_speed = axis.config.get("creep_speed", int, default=800)
        axis.creep_steps = axis.config.get("creep_steps", int, default=0)
        axis.limit_decel = axis.config.get("limit_decel", int, default=2000000)
        axis.settling_time = axis.config.get("settling_time", int, default=100)
        #        axis.backoff_steps = axis.config.get("backoff_steps", int, default=0)
        axis.window = axis.config.get("window", int, default=4)
        axis.threshold = axis.config.get("threshold", int, default=50)
        axis.tracking = axis.config.get("tracking", int, default=4000)
        axis.timeout = axis.config.get("timeout", int, default=8000)
        axis.soft_limit_enable = axis.config.get("soft_limit_enable", int, default=1)
        axis.low_limit = axis.config.get("low_limit", int, default=-2000000000)
        axis.high_limit = axis.config.get("high_limit", int, default=2000000000)
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
        self.io_command("SV", axis.channel, axis.slewrate)
        # Set acceleration of axis (steps/sec/sec)
        self.io_command("SA", axis.channel, axis.accel)
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
            self.io_command("UL", axis.channel, axis.high_limit)
            # Set the axis lower soft limit position (steps)
            self.io_command("LL", axis.channel, axis.low_limit)
        # Set encoder ratio
        cmd = "ER%d/%d" % (axis.encoder_ratio_numerator, axis.encoder_ratio_denominator)
        self.io_command(cmd, axis.channel)
        # Set gearbox ratio numerator
        self.io_command("GN", axis.channel, axis.gearbox_ratio_numerator)
        # Set gearbox ratio denominator
        self.io_command("GD", axis.channel, axis.gearbox_ratio_denominator)

    def finalize_axis(self):
        log.debug("finalize_axis() called")
        pass

    def initialize_encoder(self, encoder):
        log.debug("initialize_encoder() called")
        encoder.channel = encoder.config.get("address")
        log.debug("Encoder channel " + encoder.channel)

    def read_position(self, axis):
        log.debug("read_position() called")
        return float(self.io_command("OC", axis.channel))

    def read_encoder(self, encoder):
        log.debug("read_encoder() called")
        log.debug("Encoder channel " + encoder.channel)
        return float(self.io_command("OA", encoder.channel))

    def read_acceleration(self, axis):
        log.debug("read_acceleration() called")
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        return int(tokens[8])

    def read_deceleration(self, axis):
        log.debug("read_deceleration() called")
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        print(tokens[11])
        return int(tokens[11])

    def read_velocity(self, axis):
        log.debug("read_velocity() called")
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        return int(tokens[5])

    def read_firstvelocity(self, axis):
        log.debug("read_firstvelocity() called")
        reply = self.io_command("QS", axis.channel)
        tokens = reply.split()
        return int(tokens[2])

    def set_velocity(self, axis, velocity):
        log.debug("set_velocity() called")
        if velocity > MAX_VELOCITY or velocity < MIN_VELOCITY:
            log.error("PM600 Error: velocity out of range")
        reply = self.io_command("SV", axis.channel, velocity)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to set_velocity" + reply)

    def set_firstvelocity(self, axis, creep_speed):
        log.debug("set_firstvelocity() called")
        if creep_speed > MAX_CREEP_SPEED or velocity < MIN_CREEP_SPEED:
            log.error("PM600 Error: creep_speed out of range")
        reply = self.io_command("SC", axis.channel, creep_speed)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to set_firstvelocity" + reply)

    def set_acceleration(self, axis, acceleration):
        log.debug("set_acceleration() called")
        if acceleration > MAX_ACCELERATION or acceleration < MIN_ACCELERATION:
            log.error("PM600 Error: acceleration out of range")
        reply = self.io_command("SA", axis.channel, acceleration)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to set_acceleration" + reply)

    def set_deceleration(self, axis, deceleration):
        log.debug("set_deceleration() called")
        if deceleration > MAX_DECELERATION or deceleration < MIN_DECELERATION:
            log.error("PM600 Error: deceleration out of range")
        reply = self.io_command("SD", axis.channel, deceleration)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to set_deceleration" + reply)

    def set_position(self, axis, position):
        log.debug("set_position() called")
        reply = self.io_command("AP", axis.channel, position)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to set_position" + reply)

    def state(self, axis):
        """
        PM600 status = "abcdefgh" where:
        a is 0 = Busy or 1 = Idle
        b is 0 = OK   or 1 = Error (abort, tracking, stall, timeout etc.)
        c is 0 = Upper hard limit is OFF or 1 = Upper hard limit is ON
        d is 0 = Lower hard limit is OFF or 1 = Lower hard limit is ON
        e is 0 = Not jogging or joystick moving or 1 = Jogging or joystick moving
        f is 0 = Not at datum sensor point or 1 = On datum sensor point
        g is 0 = Future use or 1 = Future use
        h is 0 = Future use or 1 = Future use
        """
        log.debug("state() called")
        status = self.io_command("OS", axis.channel)
        log.debug("state() status:" + status)
        if status[1:2] == "1" or (status[2:3] == "1" and status[3:4] == "1"):
            log.debug("state() is fault")
            return AxisState("FAULT")
        if status[2:3] == "1":
            log.debug("state() is positive limit")
            return AxisState("LIMPOS")
        if status[3:4] == "1":
            log.debug("state() is negative limit")
            return AxisState("LIMNEG")
        if status[0:1] == "0":
            log.debug("state() is moving")
            return AxisState("MOVING")
        else:
            log.debug("state() is ready")
            return AxisState("READY")

    def prepare_move(self, motion):
        log.debug("prepare_move() called")
        pass

    def start_one(self, motion):
        log.debug("start_one() called")
        reply = self.io_command("MA", motion.axis.channel, motion.target_pos)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to move absolute" + reply)

    def stop(self, motion):
        log.debug("stop() called")
        reply = self.io_command("ST", motion.axis.channel)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to stop" + reply)

    def start_all(self, *motion_list):
        log.debug("start_all() called")
        for motion in motion_list:
            self.start_one(motion)

    def stop_all(self, *motion_list):
        log.debug("stop_all() called")
        for motion in motion_list:
            self.stop(motion)

    def home_search(self, axis, switch):
        reply = self.io_command("DM00100000", axis.channel)
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to datum mode" + reply)
        reply = self.io_command("HD", axis.channel, (+1 if switch > 0 else -1))
        if reply != "OK":
            log.error("PM600 Error: Unexpected response to home to datum" + reply)

    def home_state(self, axis):
        log.debug("home_state() called")
        return self.state(axis)

    def get_info(self, axis):
        log.debug("get_info() called")
        nlines = 23
        cmd = axis.channel + "QA\r"
        ans = self.sock.write_readlines(cmd.encode(), nlines, eol="\r\n", timeout=5)
        reply_list = ans.decode()
        # Strip the echoed command from the first reply
        idx = reply_list[0].find("\r")
        if idx == -1:
            log.error("PM600 Error: No echoed command")
        answer = reply_list[0][idx + 1 :]
        for i in range(1, nlines):
            answer = answer + "\n" + reply_list[i]
        log.debug(answer)
        return answer

    def io_command(self, command, channel, value=None):
        log.debug("io_command() called")
        if value:
            cmd = channel + command + str(value) + "\r"
            log.debug("io_command() sending command " + cmd[:-1])
        else:
            cmd = channel + command + "\r"
            log.debug("io_command() sending command " + cmd[:-1])

        ans = self.sock.write_readline(cmd.encode(), eol="\r\n")
        reply = ans.decode()
        # The response from the PM600 is terminated with CR/LF.  Remove these
        newreply = reply.rstrip("\r\n")
        # The PM600 always echoes the command sent to it, before sending the response.  It is terminated
        # with a carriage return.  So we need to delete all characters up to and including the first
        # carriage return
        idx = newreply.find("\r")
        if idx == -1:
            log.error("PM600 Error: No echoed command")
        answer = newreply[idx + 1 :]
        # check for the error character !
        idx = answer.find("!")
        if idx != -1:
            log.error("PM600 Error: " + answer[idx:])
        # Now remove the channel from the reply and check against the requested channel
        idx = answer.find(":")
        replied_channel = int(answer[:idx])
        if int(channel) != replied_channel:
            log.error("PM600 Error: Wrong channel replied %s" % replied_channel)
        log.debug("io_command() reply " + answer[idx + 1 :])
        return answer[idx + 1 :]

    def abort(self):
        log.debug("abort() called")
        return self.io_command("AB", axis.channel)

    def get_id(self, axis):
        log.debug("get_id called")
        return self.io_command("ID", axis)

    def raw_write_read(self, command):
        log.debug("raw_write_read() called")
        reply = self.sock.write_readline(command.encode(), eol="\r\n")
        return reply.decode()

    def raw_write(self, command):
        log.debug("raw_write() called")
        self.sock.write(command.encode())

    """
    PM600 added commands
    """

    @object_method(types_info=("None", "None"))
    def Reset(self, axis):
        log.debug("Reset() called")
        # Reset the controller
        self.io_command("RS", axis.channel)

    @object_method(types_info=("None", "float"))
    def GetDeceleration(self):
        return self.read_deceleration(axis)

    @object_method(types_info=("float", "None"))
    def SetDeceleration(self, axis, deceleration):
        return self.set_deceleration(axis, deceleration)
