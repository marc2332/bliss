# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from warnings import warn

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import AxisState
from bliss.common.utils import object_method

from bliss.comm.util import get_comm, TCP


"""
Bliss controller for ethernet FlexDC piezo-motor controller.
Cyril Guilloud ESRF BLISS January 2014

NOT DONE :
*Dead band
"""


class FlexDC(Controller):

    # Init of controller.
    def initialize(self):
        try:
            self.sock = get_comm(self.config.config_dict, ctype=TCP, port=4000)
        except ValueError:
            host = config.get("host")
            warn("'host' keyword is deprecated. Use 'tcp' instead", DeprecationWarning)
            comm_cfg = {"tcp": {"url": host}}
            self.sock = get_comm(comm_cfg, port=4000)

    def finalize(self):
        self.sock.close()

    # Init of each axis.
    def initialize_axis(self, axis):

        axis.channel = axis.config.get("channel")

        if axis.channel == "X":
            self.ctrl_axis = axis

        axis.target_radius = axis.config.get("target_radius", int)
        axis.target_time = axis.config.get("target_time", int)
        axis.min_dead_zone = axis.config.get("min_dead_zone", int)
        axis.max_dead_zone = axis.config.get("max_dead_zone", int)
        axis.smoothing = axis.config.get("smoothing", int)
        axis.deceleration = axis.config.get("deceleration", float)

        # Enabling servo mode.
        self._flexdc_query("%sMO=1" % axis.channel)

        # Sets "point to point" motion mode.
        # 0 -> point to point
        # ( 1 -> jogging ;    2 -> position based gearing    )
        # ( 5 -> position based ECAM ;    8 -> Step command (no profile) )
        self._flexdc_query("%sMM=0" % axis.channel)

        # Special motion mode attribute parameter
        # 0 -> no special mode
        # ( 1 -> repetitive motion )
        self._flexdc_query("%sSM=0" % axis.channel)

        # Defines smoothing (typically 4).
        self._flexdc_query("%sWW=%d" % (axis.channel, axis.smoothing))

        # Target Time (settling time?)
        self.flexdc_parameter(axis, "TT", axis.target_time)

        # Target Radius (target window ?)
        self.flexdc_parameter(axis, "TR", axis.target_radius)

        # Checks if closed loop parameters have been set.
        _ans = self._flexdc_query("%sTT" % axis.channel)
        if _ans == "0":
            elog.error("Missing closed loop param TT (Target Time)!!")

        _ans = self._flexdc_query("%sTR" % axis.channel)
        if _ans == "0":
            elog.error("Missing closed loop param TR (Target Radius)!!")

        # Minimum dead zone
        self.flexdc_parameter(axis, "CA[36]", axis.min_dead_zone)

        # Maximum dead zone
        self.flexdc_parameter(axis, "CA[37]", axis.max_dead_zone)

    def initialize_encoder(self, encoder):
        encoder.channel = encoder.config.get("channel")

    def read_position(self, axis):
        """
        Returns position's setpoint or measured position (in steps).
        """
        """ DP : Desired Position
        When an axis is in motion, DP holds the real time servo
        loop control reference position
        """
        _pos = int(self._flexdc_query("%sDP" % axis.channel))
        elog.debug("FLEXDC *setpoint* position (in steps) : %d" % _pos)
        return _pos

    def read_encoder(self, encoder):
        """ PS : Position from Sensor """
        _pos = int(self._flexdc_query("%sPS" % encoder.channel))
        elog.debug("FLEXDC *measured* position (in steps) : %d" % _pos)
        return _pos

    def read_velocity(self, axis):
        _velocity = float(self._flexdc_query("%sSP" % axis.channel))
        elog.debug("FLEXDC read velocity : %g" % _velocity)
        return _velocity

    def set_velocity(self, axis, new_velocity):
        elog.debug("FLEXDC write velocity (new_velocity=%g)" % new_velocity)
        self._flexdc_query("%sSP=%d" % (axis.channel, new_velocity))
        return self.read_velocity(axis)

    def state(self, axis):
        _ret = 0

        # Motion Status : MS command
        # bit 0 : 0x01 : In motion.
        # bit 1 : 0x02 : In stop.
        # bit 2 : 0x04 : In acceleration.
        # bit 3 : 0x08 : In deceleration.
        # bit 4 : 0x10 : Waiting for input to start motion.
        # bit 5 : 0x20 : In PTP stop (decelerating to target).
        # bit 6 : 0x40 : Waiting for end of WT period.
        _ansMS = int(self._flexdc_query("%sMS" % axis.channel))

        if _ansMS & 0x01:
            _ret = AxisState("MOVING")
        else:
            _ret = AxisState("READY")

        elog.debug("state : %s" % _ret)
        return _ret

    def prepare_move(self, motion):
        elog.debug("prepare_move, motion.target_pos=%g" % motion.target_pos)
        # Prepare axis movement.
        self._flexdc_query("%sAP=%d" % (motion.axis.channel, int(motion.target_pos)))

    def start_one(self, motion):
        elog.debug("start_one, motion.target_pos=%g" % motion.target_pos)
        # Start prepared movement.
        self._flexdc_query("%sBG" % motion.axis.channel)

    def stop(self, axis):
        elog.debug("FLEXDC stop")
        self._flexdc_query("%sST" % axis.channel)

    def home_search(self, axis, switch):
        """
        start home search.
        """
        _home_cmd = "%sQE,#HINX_X" % axis.channel
        self._flexdc_query(_home_cmd)

    def home_state(self, axis):
        _home_query_cmd = "%sQF1" % axis.channel
        _ans = self._flexdc_query(_home_query_cmd)
        if _ans == "1":
            return AxisState("MOVING")
        else:
            return AxisState("READY")

    """
    FlexDC specific.
    """

    def raw_write_read(self, cmd):
        _cmd = "%s%s" % (self.ctrl_axis.channel, cmd)
        elog.debug("raw_write_read : _cmd=%s" % _cmd)
        return self._flexdc_query(_cmd)

    def read_acceleration(self, axis):
        """
        returns acceleration read from flexdc controller in steps/s2
        """
        _acc_spss = float(self._flexdc_query("%sAC" % axis.channel))
        elog.debug("read Acceleration : _acc_spss=%g " % _acc_spss)
        return _acc_spss

    def set_acceleration(self, axis, new_acc):
        """
        Writes acceleration.
        <new_acc> is in steps/s2
        Flexdc works in steps/s2
        """
        self._flexdc_query("%sAC=%d" % (axis.channel, new_acc))
        elog.debug("write Acceleration : new_acc=%g" % new_acc)
        return axis.settings.get("acceleration")

    def _flexdc_query(self, cmd):
        # Adds "\r" at end of command.
        # TODO : test if already present ?

        elog.debug("SENDING : %s" % cmd)
        _cmd = cmd + "\r"

        # Adds ACK character:
        _cmd = _cmd + "Z"
        _ans = self.sock.write_readline(_cmd, eol=">Z")
        return _ans

    def get_id(self, axis):
        _cmd = "%sVR" % axis.channel
        return self._flexdc_query(_cmd)

    def flexdc_parameter(self, axis, param, value=None):
        """
        SET / GET parameter
        """
        if value:
            _cmd = "%s%s=%d" % (axis.channel, param, value)
            self._flexdc_query(_cmd)
            return value
        else:
            _cmd = "%s%s" % (axis.channel, param)
            return self._flexdc_query(_cmd)

    def flexdc_in_target(self, axis):
        """
        In Traget : Status register bit 6
        """
        _cmd = "%sSR" % axis.channel
        _ans = int(self._flexdc_query(_cmd))

        # Returns True if bit 6 of status register is set.
        if _ans & 32:
            return True
        else:
            return False

    def flexdc_em(self, axis):
        """
        EM : End of motion status.
        Returns a 2-uple of strings (EM CODE, Description).
        """
        _cmd = "%sEM" % axis.channel
        _ans = int(self._flexdc_query(_cmd))

        _reasons = [
            ("EM_IN_MOTION", "In motion, or After Boot up."),
            ("EM_NORMAL", "Last Motion ended Normally."),
            ("EM_FLS", "Last Motion ended due to Hardware FLS."),
            ("EM_RLS", "Last Motion ended due to Hardware RLS."),
            ("EM_HL", "Last Motion ended due to Software HL."),
            ("EM_LL", "Last Motion ended due to Software LL."),
            ("EM_MF", "Last Motion ended due to Motor Fault (see MF)."),
            ("EM_USER_STOP", "Last Motion ended due to User Stop (ST or AB)."),
            ("EM_MOTOR_OFF", "Last Motion ended due to Motor OFF (MO=0)."),
            ("EM_BAD_PROFILE_PARAM", "Last Motion ended due to Bad ECAM Parameters."),
        ]

        return _reasons[_ans]

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
            ("VL", "Actual Velocity"),  # Is this true?
            ("WW", "Smoothing"),
        ]

        _txt = ""
        for i in _infos:
            _cmd = "%s%s" % (axis.channel, i[0])
            _txt = _txt + "%35s %8s = %s \n" % (i[1], i[0], self._flexdc_query(_cmd))

        (_emc, _emstr) = self.flexdc_em(axis)
        _txt = _txt + "%35s %8s = %s \n" % (_emstr, "EM", _emc)

        return _txt
