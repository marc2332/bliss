"""
Bliss controller for ethernet NewFocus 87xx series piezo controller.
A. Beteva, M. Guijarro, ESRF BCU
"""
import time
from warnings import warn

from bliss.controllers.motor import Controller
from bliss.common import log
from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from bliss.common import event
import gevent.lock

DELAY = 0.02  # delay between 2 commands


class NF8753(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.__current_selected_channel = None
        self.lock = gevent.lock.RLock()
        self.__busy = False

    def initialize(self):
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        try:
            self.sock = get_comm(self.config.config_dict, TCP, port=23)
        except ValueError:
            host = self.config.get("host")
            warn("'host' keyword is deprecated. Use 'tcp' instead", DeprecationWarning)
            comm_cfg = {"tcp": {"url": host}}
            self.sock = get_comm(comm_cfg, port=23)

        if "=2" in self._write_read(None, "DRT", raw=True):
            raise RuntimeError(
                "Uncompatible closed-loop driver detected in daisy chain"
            )

    def finalize(self):
        self.sock.close()
        # this controller can't reconnect immediately
        # after socket is disconnected, so we put a delay here to make sure
        # socket is really closed on the controller side
        time.sleep(5 * DELAY)

    def initialize_axis(self, axis):
        axis.driver = axis.config.get("driver", str)
        axis.channel = axis.config.get("channel", int)
        axis.accumulator = None

        event.connect(axis, "move_done", self._axis_move_done)

        # self._write_no_reply(axis, "JOF") #, raw=True)
        self._write_no_reply(axis, "MON %s" % axis.driver)

    def _select_channel(self, axis):
        change_channel = "CHL %s=%d" % (axis.driver, axis.channel)
        if change_channel != self.__current_selected_channel:
            self.__current_selected_channel = change_channel
            self._write_no_reply(None, change_channel)

    def _write_no_reply(self, axis, cmd_string):
        with self.lock:
            if not cmd_string.endswith("\r\n"):
                cmd_string += "\r\n"
            if axis is not None:
                self._select_channel(axis)
            # print 'sending', cmd_string
            self.sock.write_readline(cmd_string.encode(), eol=b">")
            time.sleep(DELAY)

    def _write_read(self, axis, cmd_string, eol="\r\n>", raw=False):
        with self.lock:
            if not cmd_string.endswith("\r\n"):
                cmd_string += "\r\n"

            if axis is not None:
                self._select_channel(axis)

            # print 'sending', cmd_string, 'waiting for reply...'
            ans = self.sock.write_readline(cmd_string.encode(), eol=eol.encode())
            time.sleep(DELAY)
            # print 'reply=', ans

            ans = ans.decode()
            ans = ans.replace(">", "")
            if raw:
                return ans
            else:
                return ans.split("=")[1].split("\r\n>")[0]

    def read_velocity(self, axis):
        return int(self._write_read(axis, "VEL %s %d" % (axis.driver, axis.channel)))

    def set_velocity(self, axis, new_velocity):
        # self._write_no_reply(axis, "VEL %s %s=%d" % (axis.driver, axis.channel, new_velocity))
        return self.read_velocity(axis)

    def state(self, axis):
        if self.__busy:
            return AxisState("BUSY")
        sta = self._write_read(axis, "STA", eol="\r\n>", raw=True)
        for line in sta.split("\n"):
            if line.startswith(axis.driver):
                status_byte = int(line.split("=")[-1], 16)
                if status_byte & 0x0000001:
                    return AxisState("MOVING")
                else:
                    return AxisState("READY")

    def prepare_move(self, motion):
        self.__busy = True
        self.__moving_axis = motion.axis
        if self.__moving_axis.accumulator is None:
            _accu = (
                self.__moving_axis.settings.get("offset")
                * self.__moving_axis.steps_per_unit
            )
            self.__moving_axis.accumulator = _accu
        self.__moving_axis.accumulator += motion.delta

    def _axis_move_done(self, done):
        if done:
            # print ">"*10, "AXIS MOVE DONE"
            self.__busy = False
            self.__moving_axis.position(
                self.__moving_axis.accumulator / self.__moving_axis.steps_per_unit
            )

    def start_one(self, motion):
        # print "in motion start_one for axis", motion.axis.name
        self._write_no_reply(
            motion.axis, "REL %s=%d G" % (motion.axis.driver, motion.delta)
        )

    def stop(self, axis):
        self._write_no_reply(axis, "HAL")
