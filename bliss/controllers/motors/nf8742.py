"""
Bliss controller for ethernet NewFocus 8742 piezo controller.
A. Beteva, M. Guijarro, ESRF BCU
"""
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
import requests
import itertools


class NF8742(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.host = self.config.get("host")

    def initialize(self):
        pass

    def initialize_axis(self, axis):
        axis.channel = axis.config.get("channel", int)

    def _execute(self, axis, cmd):
        comment = "<!--#response-->"
        r = requests.get(
            "http://%s/cmd_send.cgi" % self.host,
            params={"cmd": "%d%s" % (axis.channel, cmd), "submit": "Send"},
        )
        i = r.text.find(comment)
        ans = "".join(
            itertools.takewhile(
                lambda c: c.isalnum() or c == "-", r.text[i + len(comment) :]
            )
        )
        return ans

    def read_position(self, axis):
        """
        Returns position's setpoint (in steps).
        """
        return float(self._execute(axis, "TP?"))

    def read_velocity(self, axis):
        return int(self._execute(axis, "VA?"))

    def set_velocity(self, axis, new_velocity):
        self._execute(axis, "VA%d" % new_velocity)
        return self.read_velocity(axis)

    def read_acceleration(self, axis):
        return int(self._execute(axis, "AC?"))

    def set_acceleration(self, axis, new_acc):
        self._execute(axis, "AC%d" % new_acc)

    def state(self, axis):
        sta = self._execute(axis, "MD?")
        if sta == "0":
            return AxisState("MOVING")
        else:
            return AxisState("READY")

    def start_one(self, motion):
        self._execute(motion.axis, "PR%d" % motion.delta)

    def stop(self, axis):
        self._execute(axis, "ST")
