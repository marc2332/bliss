"""
Bliss controller for Microdiff model MD2 and MD2S, using the EMBL Exporter
protocol for communication.
"""
from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING

from bliss.comm.Exporter import ExporterChannel
from bliss.comm.Exporter import ExporterCommand


class MD2(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        self.addr_dict = []
        host, port = self.config.get("exporter_address").split(":")
        self.addr_dict["address"] = host
        self.addr_dict["port"] = int(port)
        self.pos_attr_suffix = "Position"
        self.state_cmd = "getMotorState"
        

    def initialize(self):
        """
        send a command to get the state ro check if the MD2 application replies
        """
        pass

    def initialize_axis(self, axis):
        axis.root_name = axis.config.get("root_name")


    def read_position(self, axis, measured=False):
        """
        Returns position's setpoint or measured position (in steps).
        """
        if measured:
            return float(self._galil_query("TD %s" % axis.channel))
        else:
            return float(self._galil_query("TP %s" % axis.channel))

