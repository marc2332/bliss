from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING

from PyTango.gevent import DeviceProxy

"""
Bliss controller tango bliss motor
TangoEMot
Cyril Guilloud ESRF BLISS November 2014

This can be used to interface a motor instanciated on a remote
computer.
"""

class TangoEMot(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        # Gets DS name from xml config.
        self.ds_name = self.config.get("ds_name")

    def initialize(self):
        pass

    def finalize(self):
        pass

    def initialize_axis(self, axis):
        self.axis_proxy = DeviceProxy(self.ds_name)

    def read_position(self, axis, measured=False):
        """
        Returns position's setpoint or measured position.
        """
        if measured:
            return self.axis_proxy.position()
        else:
            return self.axis_proxy.measured_position()

    def read_velocity(self, axis):
        return self.axis_proxy.velocity()

    def set_velocity(self, axis, new_velocity):
        return self.axis_proxy.velocity(new_velocity)

    def state(self, axis):
        return self.axis_proxy.state()

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        self.axis_proxy.position(motion.target_pos)

    def stop(self, axis):
        self.axis_proxy.Abort()

    def home_search(self, axis):
        self.axis_proxy.GoHome()

    def home_state(self, axis):
        _home_query_cmd = "%sQF1" % axis.channel
        _ans = self._flexdc_query(_home_query_cmd)
        if _ans == "1":
            return MOVING
        else:
            return READY


    def get_info(self, axis):
        """
        Returns information about controller.
        Can be helpful to tune the device.
        """
        # list of commands and descriptions
        _infos = [

            ("VR,0", "VR,0"),
            ("VR,1", "VR,1"),
            ("VR,2", "VR,2"),
            ("VR,3", "VR,3"),
            ("VR,4", "VR,4"),
            ("VR,5", "VR,5"),
            ("VR,6", "VR,6"),

            ("AC", "Acceleration"),
            ("AD", "Analog Input Dead Band"),
            ("AF", "Analog Input Gain Factor"),
            ("AG", "Analog Input Gain"),
            ("AI", "Analog Input Value"),
            ("AP", "Next Absolute Position Target"),
            ("AS", "Analog Input Offset"),
            ("CA[36]", "Min dead zone"),
            ("CA[37]", "Max dead zone"),
            ("CA[33]", "Dead zone bit#1"),
            ("CG", "Axis Configuration"),
            ("DC", "Deceleration"),
            ("DL", "Limit deceleration"),
            ("DO", "DAC Analog Offset"),
            ("DP", "Desired Position"),
            ("EM", "Last end of motion reason"),
            ("ER", "Maximum Position Error Limit"),
            ("HL", "High soft limit"),
            ("IS", "Integral Saturation Limit"),
            ("KD[1]", "PIV Differential Gain"),
            ("KD[2]", "PIV Differential Gain (Scheduling)"),
            ("KI[1]", "PIV Integral Gain"),
            ("KI[2]", "PIV Integral Gain (Scheduling)"),
            ("KP[1]", "PIV Proportional Gain"),
            ("KP[2]", "PIV Proportional Gain (Scheduling)"),
            ("LL", "Low soft limit"),
            ("ME", "Master Encoder Axis Definition"),
            ("MF", "Motor Fault Reason"),
            ("MM", "Motion mode"),
            ("MO", "Motor On"),
            ("MS", "Motion Status"),
            ("NC", "No Control (Enable open loop)"),
            ("PE", "Position Error"),
            ("PO", "PIV Output"),
            ("PS", "Encoder Position Value"),
            ("RP", "Next Relative Position Target"),
            ("SM", "Special motion mode"),
            ("SP", "Velocity"),
            ("SR", "Status Register"),
            ("TC", "Torque (open loop) Command"),
            ("TL", "Torque Limit"),
            ("TR", "Target Radius"),
            ("TT", "Target Time"),
            ("VL", "Actual Velocity"),   # Is this true?
            ("WW", "Smoothing")]

        _txt = ""
        for i in _infos:
            _cmd = "%s%s" % (axis.channel, i[0])
            _txt = _txt + "%35s %8s = %s \n" % (
                i[1], i[0], self._flexdc_query(_cmd))

        (_emc, _emstr) = self.flexdc_em(axis)
        _txt = _txt + "%35s %8s = %s \n" % (_emstr, "EM", _emc)

        return _txt
