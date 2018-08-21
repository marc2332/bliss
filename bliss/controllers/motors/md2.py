"""
Bliss controller for Microdiff model MD2 and MD2S, using the EMBL Exporter
protocol for communication.
"""
from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import AxisState
from bliss.comm.Exporter import *
import time
import gevent


class MD2(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        host, port = self.config.get("exporter_address").split(":")
        self._exporter = Exporter(host, int(port))
        self.pos_attr_suffix = "Position"
        self.state_cmd = "getMotorState"

    def initialize(self):
        """
        Read the state to check if the MD2 application replies
        """
        self._get_swstate()

    def initialize_axis(self, axis):
        axis.root_name = axis.config.get("root_name")

    def read_position(self, axis):
        cmd = axis.root_name + self.pos_attr_suffix
        return self._exporter.readProperty(cmd)

    def state(self, axis):
        state = self._exporter.execute(self.state_cmd, axis.root_name)
        return AxisState(state.upper())

    def start_one(self, motion):
        cmd = motion.axis.root_name + self.pos_attr_suffix
        print motion.target_pos
        self._exporter.writeProperty(cmd, motion.target_pos)

    def stop(self, axis):
        self._exporter.execute("abort")

    def home_search(self, axis, switch=None):
        self._exporter.execute("startHomingMotor", axis.root_name)
        self._wait_ready(40)

    def home_state(self, axis):
        return self.state(axis)

    def _get_hwstate(self):
        try:
            return self._exporter.readProperty("HardwareState")
        except Exception:
            return "Ready"

    def _get_swstate(self):
        return self._exporter.readProperty("State")

    def _ready(self):
        if self._get_swstate() == "Ready" and self._get_hwstate() == "Ready":
            return True
        return False

    def _wait_ready(self, timeout=3):
        with gevent.Timeout(timeout):
            while not self._ready():
                gevent.sleep(0.01)
