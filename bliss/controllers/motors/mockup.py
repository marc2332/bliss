from bliss.controllers.motor import Controller
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup
import random
import math
import time

class Mockup(Controller):
  def __init__(self, name, config, axes):
    Controller.__init__(self, name, config, axes)

    self._axis_moves = {}

    # Access to the config.
    self.config.get("host")

    # add a setting of type 'int'
    # velocity is automatically added
    self.axis_settings.add('init_count', int)


  '''
  '''
  def initialize(self):
    # hardware initialization
    for axis_name, axis in self.axes.iteritems():
      axis.settings.set('init_count', 0)
      # set initial speed
      axis.settings.set('velocity', axis.config.get("velocity", float))


  '''
  '''
  def initialize_axis(self, axis):
    self._axis_moves[axis] = { "end_t": 0, "end_pos": random.randint(0,360) }

    # this is to test axis are initialized only once
    axis.settings.set('init_count', axis.settings.get('init_count')+1)


  '''
  '''
  def start_move(self, axis, target_pos, delta):
    t0 = time.time()
    pos = self.position(axis)
    v = self.velocity(axis)*axis.step_size()
    self._axis_moves[axis] = { "start_pos": pos,
                               "delta": delta,
                               "end_pos": target_pos,
                               "end_t": t0 + math.fabs(delta)/float(v),
                               "t0": t0 }


  '''
  '''
  def position(self, axis, new_position=None, measured=False):
    if self._axis_moves[axis]["end_t"]:
      # motor is moving
      t = time.time()
      v = self.velocity(axis)*axis.step_size()
      d = math.copysign(1, self._axis_moves[axis]["delta"])
      dt = t - self._axis_moves[axis]["t0"]
      pos = self._axis_moves[axis]["start_pos"] + d*dt*v
      return pos
    else:
      return self._axis_moves[axis]["end_pos"]


  '''
  '''
  def velocity(self, axis, new_velocity=None):
    if new_velocity:
      axis.settings.set('velocity', new_velocity)

    # Always return velocity. 
    return axis.settings.get('velocity')


  '''
  '''
  def read_state(self, axis):
    if self._axis_moves[axis]["end_t"] > time.time():
      return MOVING
    else:
      self._axis_moves[axis]["end_t"]=0
      return READY


  '''
  '''
  def stop(self, axis):
    self._axis_moves[axis]["end_pos"]=self.position(axis)
    self._axis_moves[axis]["end_t"]=0


