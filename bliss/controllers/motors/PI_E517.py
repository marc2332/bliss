from bliss.controllers.motor import Controller
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup
import functools
import random
import math
import time

import pi_gcs
from bliss.comm import tcp

"""
Bliss controller for ethernet PI E517 piezo controller.
Cyril Guilloud ESRF BLISS
Thu 13 Feb 2014 15:51:41
"""

class PI_E517(Controller):
  def __init__(self, name, config, axes):
    Controller.__init__(self, name, config, axes)

    self.host = self.config.get("host")

  # Init of controller.
  def initialize(self):
    self.sock = tcp.Socket(self.host, 50000)

  def finalize(self):
    self.sock.close()


  # Init of each axis.
  def initialize_axis(self, axis):
    # Enables the closed-loop.
    # self.sock.write("SVO 1 1\n")
    axis.channel       = axis.config.get("channel")
    axis.chan_letter   = axis.config.get("chan_letter")

    add_axis_method(axis, self.get_id)


  def position(self, axis, new_position=None, measured=False):
    if new_position is not None:
       pass

    if measured:
      _ans = self._get_pos()
    else:
      _ans = self._get_target_pos()

    return _ans


  def velocity(self, axis, new_velocity=None):
    if new_velocity is not None:
      pass

    #return self.axis_settings.get(axis, "velocity")
    return 1

  def state(self, axis):
    if self._get_closed_loop_status():
      if self._get_on_target_status():
        return READY
      else:
        return MOVING
    else:
      raise RuntimeError("closed loop disabled")


  def prepare_move(self, axis, target_pos, delta):
    self._target_pos = target_pos


  def start_move(self, axis, target_pos, delta):
    self.sock.write("MOV 1 %g\n"%self._target_pos)


  def stop(self, axis):
    # to check : copy of current position into target position ???
    self.sock.write("STP\n")


  """
  E517 specific communication
  """

  def send(self, axis, cmd):
    _chan = axis.channel
    _cmd = cmd + "\n"
    print "Send %s to %s"%(cmd, _chan)
    _ans = self.sock.write_readline(_cmd)

    return _ans

  def send_no_ans(self, axis, cmd):
    _chan = axis.channel
    _cmd = cmd + "\n"
    print "Send %s to %s"%(cmd, _chan)
    self.sock.write(_cmd)


  def _get_pos(self, axis):
    '''
    Returns real position read by capcitive captor.
    '''
    _ans = self.send("POS? %s"%axis.chan_letter)

    print "position POS:", _ans

    # _ans should looks like ""
    # "\n" removed by tcp lib.
    # _pos = float(_ans[2:])

    return _pos

#  def _get_target_pos(self):
#    '''
#    Returns last target position (setpoint value).
#    '''
#    _ans = self.sock.write_readline("MOV?\n")
#
#    # _ans should looks like "1=-8.45709419e+01\n"
#    # "\n" removed by tcp lib.
#    _pos = float(_ans[2:])
#
#    return _pos
#
  def get_id(self, axis):
    return self.send(axis, "IDN?\n")

#  def _get_closed_loop_status(self):
#    _ans = self.sock.write_readline("SVO?\n")
#
#    if _ans == "1=1":
#      return True
#    elif _ans == "1=0":
#      return False
#    else:
#      return -1
#
#  def _get_on_target_status(self):
#    _ans = self.sock.write_readline("ONT?\n")
#
#    if _ans =="":
#      return True
#    elif _ans =="":
#      return False
#    else:
#      return -1
#
#  def _get_error(self):
#    _error_number = self.sock.write_readline("ERR?\n")
#    _error_str = pi_gcs.get_error_str(_error_number)
#
#    return (_error_number, _error_str)
#
#  def _stop(self):
#    self.sock.write("STP\n")
#
#  def _set_velocity(self, velocity):
#    self.sock.write("VEL 1 %f\n"%velocity)
#
#  '''
#  Returns a set of usefull information about controller.
#  Can be helpful to tune the device.
#  '''
#  def _get_infos(self):
#    _infos = [
#      ("Identifier                 ", "IDN?\n"),
#      ("Com level                  ", "CCL?\n"),
#      ("Real Position              ", "POS?\n"),
#      ("Setpoint Position          ", "MOV?\n"),
#      ("Position low limit         ", "SPA? 1 0x07000000\n"),
#      ("Position High limit        ", "SPA? 1 0x07000001\n"),
#      ("Velocity                   ", "VEL?\n"),
#      ("On target                  ", "ONT?\n"),
#      ("Target tolerance           ", "SPA? 1 0X07000900\n"),
#      ("Settling time              ", "SPA? 1 0X07000901\n"),
#      ("Sensor Offset              ", "SPA? 1 0x02000200\n"),
#      ("Sensor Gain                ", "SPA? 1 0x02000300\n"),
#      ("Motion status              ", "#5\n"),
#      ("Closed loop status         ", "SVO?\n"),
#      ("Auto Zero Calibration ?    ", "ATZ?\n"),
#      ("Analog input setpoint      ", "AOS?\n"),
#      ("Low  Voltage Limit         ", "SPA? 1 0x07000A00\n"),
#      ("High Voltage Limit         ", "SPA? 1 0x07000A01\n")
#    ]
#
#    _txt = ""
#
#    for i in _infos:
#      _txt = _txt + "    %s %s\n"%(i[0],
#                        self.sock.write_readline(i[1]))
#
#    _txt = _txt + "    %s  \n%s\n"%("Communication parameters",
#                                    "\n".join(self.sock.write_readlines("IFC?\n", 5)))
#
#    _txt = _txt + "    %s  \n%s\n"%("Analog setpoints",
#                                    "\n".join(self.sock.write_readlines("TSP?\n", 2)))
#    _txt = _txt + "    %s  \n%s\n"%("ADC value of analog input",
#                                    "\n".join(self.sock.write_readlines("TAD?\n", 2)))
#
#    return _txt
#
