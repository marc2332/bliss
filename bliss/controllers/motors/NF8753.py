"""
Bliss controller for ethernet NewFocus 87xx series piezo controller.
A. Beteva, M. Guijarro, ESRF BCU
"""
import time

from bliss.controllers.motor import Controller; from bliss.common import log
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING
from bliss.comm import tcp
from bliss.common import event
import gevent.lock

DELAY = 0.02  # delay between 2 commands


class NF8753(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self.host = self.config.get("host")
        self._current_selected_channel = None
        self.lock = gevent.lock.RLock()
        self.__busy = False

    def initialize(self):
        self.sock = tcp.Socket(self.host, 23)
        if '=2' in self._write_read(None, "DRT", raw=True):
            raise RuntimeError("Uncompatible closed-loop driver detected in daisy chain")

    def finalize(self):
        """
        Closes the controller socket.
        """
        self.sock.close()
        # this controller can't reconnect immediately
        # after socket is disconnected, so we put a delay here to make sure
        # socket is really closed on the controller side
        time.sleep(DELAY)

    def initialize_axis(self, axis):
        axis.driver = axis.config.get("driver", str)
        axis.channel = axis.config.get("channel", int)

        event.connect(axis, "move_done", self._axis_move_done)
        self._write_no_reply(axis, "JOF")
        self._write_no_reply(axis, "MON")

    def read_position(self, axis, measured=False):
        # position is relative to current client connection,
        # and in case of 8753 it is just a counter of relative
        # moves
        _pos = self._write_read(axis, "POS %s" % axis.driver)
        return float(_pos)

    def _select_channel(self, axis):
        change_channel = "CHL %s=%d" % (axis.driver, axis.channel)
        if change_channel != self._current_selected_channel:
            self._current_selected_channel = change_channel
            self._write_no_reply(None, change_channel)

    def _write_no_reply(self, axis, cmd_string):
        with self.lock:
            if not cmd_string.endswith('\n'):
                cmd_string += '\n'
            if axis is not None:
                self._select_channel(axis)
            print 'sending', cmd_string
            self.sock.write_readline(cmd_string, eol='>')
            time.sleep(DELAY)

    def _write_read(self, axis, cmd_string, eol='\r\n', raw=False):
        with self.lock:
            if not cmd_string.endswith('\r\n'):
                cmd_string += '\r\n'

            if axis is not None:
                self._select_channel(axis)

            print 'sending', cmd_string, 'waiting for reply...'
            ans = self.sock.write_readline(cmd_string, eol=eol)
            time.sleep(DELAY)
            print 'reply=', ans

            ans = ans.replace(">", "")
            if raw:
                return ans
            else:
                return ans.split("=")[1].split("\r\n")[0]

    def read_velocity(self, axis):
        return int(self._write_read(axis, "VEL %s %d" % (axis.driver, axis.channel)))

    def set_velocity(self, axis, new_velocity):
        self._write_no_reply(axis, "VEL %s %d=%d" % (axis.driver, axis.channel, new_velocity))
        return self.read_velocity(axis)

    def state(self, axis):
        sta = self._write_read(axis, "STA", eol='\r\n>', raw=True)
        for line in sta.split("\n"):
            if line.startswith(axis.driver):
                status_byte = int(line.split("=")[-1], 16)
                if status_byte & 0x0000001:
                    return MOVING
                else:
                    return READY

    def is_busy(self):
        return self.__busy

    def prepare_move(self, motion):
        self.__busy = True

    def _axis_move_done(self, done):
        if done:
            print ">" * 10, "AXIS MOVE DONE"
            self.__busy = False

    def start_one(self, motion):
        print "in motion start_one for axis", motion.axis.name
        self._write_no_reply(motion.axis, "ABS %s=%d G" % (motion.axis.driver, motion.target_pos))

    def stop(self, axis):
        self._write_no_reply(axis, "HAL")
