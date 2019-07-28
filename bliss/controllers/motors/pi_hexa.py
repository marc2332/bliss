# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
import time
import gevent
from functools import wraps
from bliss.comm.util import get_comm, get_comm_type, TCP, SERIAL
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss import global_map
from .pi_gcs import get_error_str

"""
Bliss controller for controlling the Physik Instrumente hexapod
controllers 850 and 887.

The Physik Instrument Hexapod M850 is a hexapod controller with
a serial line interface.
The Physik Instrument Hexapod C887 is a hexapod controller with
a serial line and socket interfaces. Both of them can be used.

config example:
- class PI_HEXA
  model: 850 # 850 or 887 (optional)
  serial:
    url: ser2net://lid133:28000/dev/ttyR37
  axes:
    - name: hexa_x
      channel: X
    - name: hexa_y
      channel: Y
    - name: hexa_z
      channel: Z
    - name: hexa_u
      channel: U
    - name: hexa_v
      channel: V
    - name: hexa_w
      channel: W
"""


def _atomic_communication(fn):
    @wraps(fn)
    def f(self, *args, **kwargs):
        with self._cnx.lock:
            return fn(self, *args, **kwargs)

    return f


class PI_HEXA(Controller):
    COMMAND = enum.Enum(
        "PI_HEXA.COMMAND", "POSITIONS MOVE_STATE MOVE_SEP INIT STOP_ERROR"
    )

    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._cnx = None
        self.controler_model = None
        self._commands = dict()

    def initialize(self):
        """
        Initialize the communication to the hexapod controller
        """
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

        comm_type = get_comm_type(self.config.config_dict)
        comm_option = {"timeout": 30.}
        if comm_type == TCP:
            comm_option["ctype"] = TCP
            comm_option.setdefault("port", 50000)
            controler_model = self.config.get("model", int, 887)
        elif comm_type == SERIAL:
            comm_option.setdefault("baudrate", 57600)
            comm_option["ctype"] = SERIAL
            controler_model = self.config.get("model", int, 850)
        else:
            raise ValueError(
                "PI_HEXA: communication of type (%s) " "not yet managed" % comm_type
            )

        model_list = [850, 887]
        if controler_model not in model_list:
            raise ValueError(
                "PI_HEXA: model %r not managed,"
                "only managed model %r" % (controler_model, model_list)
            )
        self.controler_model = controler_model

        self._cnx = get_comm(self.config.config_dict, **comm_option)

        global_map.register(self, children_list=[self._cnx])

        commands = {
            850: {
                self.COMMAND.POSITIONS: "POS?",
                #                           self.COMMAND.MOVE_STATE : ("MOV?", lambda x: 0 if x == '1' else 1),
                self.COMMAND.MOVE_STATE: ("\5", lambda x: int(x)),
                self.COMMAND.MOVE_SEP: "",
                self.COMMAND.INIT: "INI X",
                self.COMMAND.STOP_ERROR: 2,
            },
            887: {
                self.COMMAND.POSITIONS: "\3",
                self.COMMAND.MOVE_STATE: ("\5", lambda x: int(x, 16)),
                self.COMMAND.MOVE_SEP: " ",
                self.COMMAND.INIT: "FRF X",
                self.COMMAND.STOP_ERROR: 10,
            },
        }

        self._commands = commands[controler_model]

    def finalize(self):
        if self._cnx is not None:
            self._cnx.close()

    def initialize_axis(self, axis):
        axis.channel = axis.config.get("channel", str)

    def read_position(self, axis):
        return self._read_all_positions()[axis.channel]

    @_atomic_communication
    def state(self, axis):
        cmd, test_func = self._commands[self.COMMAND.MOVE_STATE]
        moving_flag = test_func(self.command(cmd, 1))
        if moving_flag:
            self._check_error_and_raise()
            return AxisState("MOVING")
        return AxisState("READY")

    def home_state(self, axis):
        # home_search is blocking until the end,
        # so this is called when homing is done;
        # at the end of axis homing, all axes
        # have changed position => do a sync hard
        try:
            return self.state(axis)
        finally:
            for axis in self.axes.values():
                axis.sync_hard()

    def start_one(self, motion):
        self.start_all(motion)

    @_atomic_communication
    def start_all(self, *motions):
        sep = self._commands[self.COMMAND.MOVE_SEP]
        cmd = "MOV " + " ".join(
            [
                "%s%s%g" % (motion.axis.channel, sep, motion.target_pos)
                for motion in motions
            ]
        )
        self.command(cmd)
        self._check_error_and_raise()

    def stop(self, axis):
        self.stop_all()

    @_atomic_communication
    def stop_all(self, *motions):
        self.command("STP")
        self._check_error_and_raise(ignore_stop=True)

    def command(self, cmd, nb_line=None, **kwargs):
        """
        Send raw command to the controller
        """
        cmd = cmd.strip()
        need_reply = cmd.find("?") > -1 if nb_line is None else nb_line
        cmd += "\n"
        cmd = cmd.encode()
        if need_reply:
            if nb_line is not None and nb_line > 1:
                return [
                    r.decode()
                    for r in self._cnx.write_readlines(cmd, nb_line, **kwargs)
                ]
            else:
                return self._cnx.write_readline(cmd, **kwargs).decode()
        else:
            return self._cnx.write(cmd)

    @_atomic_communication
    def home_search(self, axis, switch):
        init_cmd = self._commands[self.COMMAND.INIT]
        self.command(init_cmd)
        self._check_error_and_raise(timeout=30.)

    def _read_all_positions(self):
        cmd = self._commands[self.COMMAND.POSITIONS]
        answer = self.command(cmd, nb_line=6)
        positions = dict()
        try:
            for channel_name, ans in zip(["%s=" % x for x in "XYZUVW"], answer):
                if not ans.startswith(channel_name):
                    raise RuntimeError("PI_HEXA: error parsing position answer")
                positions[channel_name[0]] = float(ans[2:])
        except:
            self._cnx.flush()
            raise
        else:
            return positions

    def _check_error_and_raise(self, ignore_stop=False, **kwargs):
        err = int(self.command("ERR?", **kwargs))
        if err > 0:
            if (
                ignore_stop and err == self._commands[self.COMMAND.STOP_ERROR]
            ):  # stopped by user
                return
            human_error = get_error_str(err)
            errors = [self.name, err, human_error]
            raise RuntimeError("Device {0} error nb {1} => ({2})".format(*errors))
