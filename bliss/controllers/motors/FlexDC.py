from bliss.controllers.motor import Controller
from bliss.controllers.motor import add_method
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup
import functools
import random
import math
import time

from bliss.comm import tcp


"""
Bliss controller for ethernet FlexDC piezo-motor controller.
Cyril Guilloud ESRF BLISS January 2014
"""

class FlexDC(Controller):
  def __init__(self, name, config, axes):
    Controller.__init__(self, name, config, axes)

    self.host = self.config.get("host")

  # Init of controller.
  def initialize(self):
    self.sock = tcp.Socket(self.host, 4000)

  def finalize(self):
    self.sock.close()

  # Init of each axis.
  def initialize_axis(self, axis):
    axis.channel = axis.config.get("channel")

    add_method(axis, "get_id", functools.partial(self._get_id, axis.channel))

    # Sets "point to point" motion mode.
    # 0 -> point to point
    # ( 1 -> jogging ;  2 -> position based gearing  )
    # ( 5 -> position based ECAM ;  8 -> Step command (no profile) )
    print self._flexdc_query("%sMM=0"%axis.channel)


    # Special motion mode attribute parameter
    # 0 -> no special mode
    # ( 1 -> repetitive motion )
    print self._flexdc_query("%sSM=0"%axis.channel)

    # Defines smoothing 4
    print self._flexdc_query("%sWW=4"%axis.channel)

    # Check if closed loop parameters have been set
    _ans = self._flexdc_query("%sTT"%axis.channel)
    if _ans == "0":
      print "Missing closed loop param TT (Target Time)!!"

    _ans = self._flexdc_query("%sTR"%axis.channel)
    if _ans == "0":
      print "Missing closed loop param TR (Target Radius)!!"


  def read_position(self, axis, measured=False):
    # position in steps
    _pos = self._flexdc_query("%sDP"%axis.channel)
    return _pos


  def read_velocity(self, axis):
    _velocity = self._flexdc_query("%sSP"%axis.channel)
    return _velocity


  def read_state(self, axis):
    ret = 0
    sta = 0

    _ansMS = self._flexdc_query("%sMS"%axis.channel)

    if(sta & (1<<0)):
      ret |= 0x02

    # return MOVING
    print "SSSSSSSSSSSTTTTTTTTEEEEEEEEEE"
    return READY


  def prepare_move(self, axis, target_pos, delta):
    pass


  def start_move(self, axis, target_pos, delta):
    pass


  def stop(self, axis):
    _ans = self._flexdc_query("%sST"%axis.channel)


  """
  FlexDC specific communication.
  """

  # 
  def _flexdc_query(self, cmd):
    # Adds "\r" at end of command.
    # TODO : test if not needed
    _cmd = cmd + "\r"

    # Adds ACK character:
    _cmd = _cmd + "Z"
    _ans = self.sock.write_readline(_cmd, eol=">" )
    if self.sock.raw_read(1) != "Z":
      print "missing ack character ???"
    return _ans

  def _get_id(self, channel):
    _cmd = "%sVR"%channel
    return self._flexdc_query(_cmd)

  '''
  Returns information about controller.
  Can be helpful to tune the device.
  '''
  def _get_infos(self, channel):

    # list of commands and descriptions
    _infos = [

    ("AC",      "Acceleration"),
    ("AD",      "Analog Input Dead Band"),
    ("AF",      "Analog Input Gain Factor"),
    ("AG",      "Analog Input Gain"),
    ("AI",      "Analog Input Value"),
    ("AP",      "Next Absolute Position Target"),
    ("AS",      "Analog Input Offset"),
    ("CA[36]",      "Min dead zone"),
    ("CA[37]",      "Max dead zone"),
    ("CA[33]",      "Dead zone bit#1"),
    ("CG",      "Axis Configuration"),
    ("DC",      "Deceleration"),
    ("DL",      "Limit deceleration"),
    ("DO",      "DAC Analog Offset"),
    ("DP",      "Desired Position"),
    ("EM",      "Last end of motion reason"),
    ("ER",      "Maximum Position Error Limit"),
    ("HL",      "High soft limit"),
    ("IS",      "Integral Saturation Limit"),
    ("KD[1]",      "PIV Differential Gain"),
    ("KD[2]",      "PIV Differential Gain (Scheduling)"),
    ("KI[1]",      "PIV Integral Gain"),
    ("KI[2]",      "PIV Integral Gain (Scheduling)"),
    ("KP[1]",      "PIV Proportional Gain"),
    ("KP[2]",      "PIV Proportional Gain (Scheduling)"),
    ("LL",      "Low  soft limit"),
    ("ME",      "Master Encoder Axis Definition"),
    ("MF",      "Motor Fault Reason"),
    ("MM",      "Motion mode"),
    ("MO",      "Motor On"),
    ("MS",      "Motion Status"),
    ("NC",      "No Control (Enable open loop)"),
    ("PE",      "Position Error"),
    ("PO",      "PIV Output"),
    ("PS",      "Encoder Position Value"),
    ("RP",      "Next Relative Position Target"),
    ("SM",      "Special motion mode"),
    ("SP",      "Velocity"),
    ("SR",      "Status Register"),
    ("TC",      "Torque (open loop) Command"),
    ("TL",      "Torque Limit"),
    ("TR",      "Target Radius"),
    ("TT",      "Target Time"),
    ("VL",      "Actual Velocity"),   # Is this true?
    ("WW",      "Smoothing")        ]

    _txt = ""
    for i in _infos:
      _cmd = "%s%s"%(channel, i[0])
      _txt = _txt + "%35s %8s = %s \n"%(i[1], i[0], self._flexdc_query(_cmd))

    return _txt

