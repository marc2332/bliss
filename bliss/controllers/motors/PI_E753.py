from bliss.controllers.motor import Controller
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup
import random
import math
import time

import pi_gcs
from bliss.comm import tcp

class PI_E753(Controller):
  def __init__(self, name, config, axes):
    Controller.__init__(self, name, config, axes)

    self.host = self.get_property("host")

  # Init of controller.
  def initialize(self):
    self.sock = tcp.Socket(self.host, 50000)

  def finalize(self):
    self.sock.close()

  # Init of each axis.
  def initialize_axis(self, axis):
    self.read_position(axis)

  @task
  def _move(self, axis, target_pos, delta):
    pass
#    def move_cleanup():
#      # trucs a faire en cas de cleanup...
#      self.update_position(axis, self.read_position(axis))
#      self.update_state(axis, READY)
#
#    with cleanup(move_cleanup):
#      self.update_state(axis, MOVING)
#
#      self.sock.write("MV %s"%target_pos)
#
#      while self.sock.write_read("ST?") == "MOVING":
#        time.sleep(0.01)
#        self.update_position(axis, self.read_position(axis))

  def read_position(self, axis, measured=False):
    return self._get_pos(axis, measured)

  def read_velocity(self, axis):
    return self.axis_settings.get(axis, "velocity")

  def read_state(self, axis):
    return self.axis_settings.get(axis, "state")

  def _get_pos(self, axis, measured=False):
    if measured:
      _ans = self.sock.write_readline("POS?\n")
    else:
      _ans = self.sock.write_readline("MOV?\n")

    # _ans should looks like "1=-8.45709419e+01\n"
    # "\n" removed by tcp lib.
    _pos = float(_ans[2:])

    axis.settings.set("position", _pos)
    # to move to eMotion layer (cf axis)
    self.update_position(axis, _pos)
    return _pos

  def _get_identifier(self):
    return self.sock.write_readline("IDN?\n")

  def _move_to_pos(self, axis, pos):
    self.sock.write("MOV 1 %g\n"%pos)
    # no update position : done in movement loop ?
    # return ?

  def _get_status(self):

    if self._get_closed_loop_status():
      return self._get_on_target_status()
    else:
      # print "closed loop disabled"
      pass

  def _get_closed_loop_status(self):
    _ans = self.sock.write_readline("SVO?\n")

    if _ans == "1=1":
      return True
    elif _ans == "1=0":
      return False
    else:
      return -1

  def _get_on_target_status(self):
    _ans = self.sock.write_readline("ONT?\n")

    if _ans =="":
      return True
    elif _ans =="":
      return False
    else:
      return -1

  def _get_error(self):
    _error_number = self.sock.write_readline("ERR?\n")
    _error_str = pi_gcs.get_error_str(_error_number)

    return (_error_number, _error_str)

  def _get_infos(self):
    _infos = [
      ("identifier                 ", "IDN?\n"),
      ("com level                  ", "CCL?\n"),
      ("Real Position              ", "POS?\n"),
      ("Setpoint Position          ", "MOV?\n"),
      ("Position low limit         ", "SPA? 1 0x07000000\n"),
      ("Position High limit        ", "SPA? 1 0x07000001\n"),
      ("ADC value of analog input  ", "TAD?\n"),
      ("Velocity                   ", "VEL?\n"),
      ("On target                  ", "ONT?\n"),
      ("target tolerance           ", "SPA? 1 0X07000900?\n"),
      ("Sensor Offset              ", "SPA? 1 0x02000200?\n"),
      ("Sensor Gain                ", "SPA? 1 0x02000300?\n"),
      ("Motion status              ", "#5\n"),
      ("Closed loop status         ", "SVO?\n"),
      ("Analog Setpoints           ", "TSP?\n"),
      ("Auto Zero Calibration ?    ", "ATZ?\n"),
      ("Low  Voltage Limit         ", "SPA? 1 0x07000A00\n"),
      ("High Voltage Limit         ", "SPA? 1 0x07000A01\n")
    ]

    _txt = ""

    for i in _infos:
      _txt = _txt + "    %s %s\n"%(i[0],
                        self.sock.write_readline(i[1]))

    return _txt

