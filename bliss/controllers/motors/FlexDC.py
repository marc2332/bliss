from bliss.controllers.motor import Controller
from bliss.controllers.motor import add_axis_method
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

NOT DONE :
*Dead band

"""


class FlexDC(Controller):
  def __init__(self, name, config, axes):
    Controller.__init__(self, name, config, axes)

    self.host = self.config.get("host")

  # Init of controller.
  def initialize(self):
    print "FLEXDC CONTROLLER initialize"
    self.sock = tcp.Socket(self.host, 4000)

  def finalize(self):
    print "FLEXDC CONTROLLER finalize"
    self.sock.close()

  # Init of each axis.
  def initialize_axis(self, axis):
    print "FLEXDC initialize_axis"

    axis.channel       = axis.config.get("channel")
    axis.target_radius = axis.config.get("target_radius", int)
    axis.target_time   = axis.config.get("target_time", int)
    axis.smoothing     = axis.config.get("smoothing", int)
    axis.acceleration  = axis.config.get("acceleration", int)
    axis.deceleration  = axis.config.get("deceleration", int)

    axis.settings.set('velocity', axis.config.get("velocity", float))

    add_axis_method(axis, self.get_id)
    add_axis_method(axis, self.get_info)


    # Enabling servo mode.
    self._flexdc_query("%sMO=1"%axis.channel)

    # Sets "point to point" motion mode.
    # 0 -> point to point
    # ( 1 -> jogging ;  2 -> position based gearing  )
    # ( 5 -> position based ECAM ;  8 -> Step command (no profile) )
    self._flexdc_query("%sMM=0"%axis.channel)

    # Special motion mode attribute parameter
    # 0 -> no special mode
    # ( 1 -> repetitive motion )
    self._flexdc_query("%sSM=0"%axis.channel)

    # Defines smoothing (typically 4).
    self._flexdc_query("%sWW=%d"%(axis.channel, axis.smoothing))

    # Target Time (settling time?)
    self.flexdc_parameter(axis, "TT", axis.target_time)

    # Target Radius (target window ?)
    self.flexdc_parameter(axis, "TR", axis.target_radius)

    # Checks if closed loop parameters have been set.
    _ans = self._flexdc_query("%sTT"%axis.channel)
    if _ans == "0":
      print "Missing closed loop param TT (Target Time)!!"

    _ans = self._flexdc_query("%sTR"%axis.channel)
    if _ans == "0":
      print "Missing closed loop param TR (Target Radius)!!"

    # Acceleration
    self._flexdc_query("%sAC=%d"%(axis.channel, axis.acceleration))

    # Deceleration
    self._flexdc_query("%sAD=%d"%(axis.channel, axis.deceleration))

    # Velocity
    self._flexdc_query("%sSP=%s"%(axis.channel, axis.velocity()))

  def position(self, axis, new_position=None, measured=False):
    if new_position is None:
      if measured:
        ''' position in steps
            PS : sensor position
        '''
        _pos = int(self._flexdc_query("%sPS"%axis.channel))
        # print "FLEXDC measured position :", _pos
        return _pos
      else:
        ''' position in steps
            DP : desired position
            When an axis is in motion, DP holds the real time servo
            loop control reference position
        '''
        _pos = int(self._flexdc_query("%sDP"%axis.channel))
        # print "FLEXDC setpoint position : %g"%(_pos)
        return _pos


  def velocity(self, axis, new_velocity=None):
    if new_velocity is None:
      _velocity = self._flexdc_query("%sSP"%axis.channel)
    else:
      self._flexdc_query("%sSP=%d"%(axis.channel, new_velocity))
      _velocity = new_velocity

    return _velocity


  def state(self, axis):
    _ret = 0
    sta = 0

    # Motion Status : MS command
    # bit 0 : 0x01 : In motion.
    # bit 1 : 0x02 : In stop.
    # bit 2 : 0x04 : In acceleration.
    # bit 3 : 0x08 : In deceleration.
    # bit 4 : 0x10 : Waiting for input to start motion.
    # bit 5 : 0x20 : In PTP stop (decelerating to target).
    # bit 6 : 0x40 : Waiting for end of WT period.
    _ansMS = int(self._flexdc_query("%sMS"%axis.channel))

    if(_ansMS & 0x01):
      _ret = MOVING
    else:
      _ret = READY

    print "FLEXDC state :", _ret
    return _ret


  def prepare_move(self, axis, target_pos, delta):
    print "FLEXDC prepare_move, target_pos=", target_pos
    self._flexdc_query("%sAP=%d"%(axis.channel, int(target_pos)))

  def start_move(self, axis, target_pos, delta):
    print "FLEXDC start_move, target_pos=", target_pos
    self._flexdc_query("%sBG"%axis.channel)

  def stop(self, axis):
    print "FLEXDC stop"
    _ans = self._flexdc_query("%sST"%axis.channel)


  '''
  FlexDC specific.
  '''

  # 
  def _flexdc_query(self, cmd):
    # Adds "\r" at end of command.
    # TODO : test if already present ?
    _cmd = cmd + "\r"

    # Adds ACK character:
    _cmd = _cmd + "Z"
    _ans = self.sock.write_readline(_cmd, eol=">" )
    if self.sock.raw_read(1) != "Z":
      print "missing ack character ??? return of cmd \"%s\". "%cmd
    return _ans

  # 
  def get_id(self, axis):
    _cmd = "%sVR"%axis.channel
    return self._flexdc_query(_cmd)


  '''
  SET / GET parameter
  '''
  def flexdc_parameter(self, axis, param, value=None):
    if value:
      _cmd = "%s%s=%d"%(axis.channel, param, value)
      self._flexdc_query(_cmd)
      return(value)
    else:
      _cmd = "%s%s"%(axis.channel, param)
      return self._flexdc_query(_cmd)

  '''
  Homing command
  '''
  def flexdc_home(self, axis):
    _cmd = "%sQE,#HINX_X"%axis.channel
    self._flexdc_query(_cmd)

  '''
  In Traget : Status register bit 6
  '''
  def flexdc_in_target(self, axis):
    _cmd = "%sSR"%axis.channel
    _ans = int(self._flexdc_query(_cmd))

    # Returns True if bit 6 of status register is set.
    if _ans & 32 :
      return True
    else:
      return False

  '''
  EM : End of motion status.
  Returns a 2-uple of strings (EM CODE, Description).
  '''
  def flexdc_em(self, axis):
    _cmd = "%sEM"%axis.channel
    _ans = int(self._flexdc_query(_cmd))


    _reasons = [
      ("EM_IN_MOTION"         , "In motion, or After Boot up."),
      ("EM_NORMAL"            , "Last Motion ended Normally."),
      ("EM_FLS"               , "Last Motion ended due to Hardware FLS."),
      ("EM_RLS"               , "Last Motion ended due to Hardware RLS."),
      ("EM_HL"                , "Last Motion ended due to Software HL."),
      ("EM_LL"                , "Last Motion ended due to Software LL."),
      ("EM_MF"                , "Last Motion ended due to Motor Fault (check MF)."),
      ("EM_USER_STOP"         , "Last Motion ended due to User Stop (ST or AB)."),
      ("EM_MOTOR_OFF"         , "Last Motion ended due to Motor OFF (MO=0)."),
      ("EM_BAD_PROFILE_PARAM" , "Last Motion ended due to Bad ECAM Parameters.")
      ]

    return _reasons[_ans]

  '''
  Returns information about controller.
  Can be helpful to tune the device.
  '''
  def get_info(self, axis):

    # list of commands and descriptions
    _infos = [

    ("VR,0",      "VR,0"),
    ("VR,1",      "VR,1"),
    ("VR,2",      "VR,2"),
    ("VR,3",      "VR,3"),
    ("VR,4",      "VR,4"),
    ("VR,5",      "VR,5"),
    ("VR,6",      "VR,6"),

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
      _cmd = "%s%s"%(axis.channel, i[0])
      _txt = _txt + "%35s %8s = %s \n"%(i[1], i[0], self._flexdc_query(_cmd))

    (_emc, _emstr) = self.flexdc_em(axis)
    _txt = _txt + "%35s %8s = %s \n"%( _emstr, "EM", _emc)

    return _txt

