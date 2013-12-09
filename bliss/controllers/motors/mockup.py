from bliss.controllers.motor import Controller
from bliss.common.motor import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup
import random
import math
import time

class Mockup(Controller):
  def __init__(self, name, config):
    Controller.__init__(self, name, config)
 
    self.host = self.config.get_property("host")
    self.port = self.config.get_property("port", int)

    self.axis_settings.add('channel', int)

    for axis_name, axis in self.axes.iteritems():
      self.axis_settings.set(axis, 'position', random.randint(0,360))
      self.axis_settings.set(axis, 'state', READY)
      self.axis_settings.set_from_config(axis, axis.config)

  @task
  def _move(self, axis, start_pos, final_pos):
    v = self.read_velocity(axis)
    d = math.copysign(1, final_pos-start_pos)
    pos = start_pos
    t0 = time.time()
    end_t = t0 + math.fabs(final_pos-start_pos)/float(v)
   
    def move_cleanup():
      self.update_state(axis, READY)
 
    with cleanup(move_cleanup):
      self.update_state(axis, MOVING)
      while True:
        t = time.time()
        if t < end_t:
          dt = t - t0
          pos += d*dt*v 
          self.update_position(axis, pos)
          time.sleep(0.01) 
        else:
          break
      self.update_position(axis, final_pos)

  def read_position(self, axis):
    return self.axis_settings.get(axis, "position")

  def read_velocity(self, axis):
    return self.axis_settings.get(axis, "velocity")

  def read_state(self, axis):
    return self.axis_settings.get(axis, "state")
