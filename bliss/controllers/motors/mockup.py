from bliss.controllers.motor import Controller
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup
from bliss.controllers.motor import add_axis_method
import random
import math
import time

class Mockup(Controller):
  def __init__(self, name, config, axes):
    Controller.__init__(self, name, config, axes)

    self._axis_moves = {}

    # Access to the config.
    self.config.get("host")

    # add a setting name 'init_count' of type 'int'
    self.axis_settings.add('init_count', int)

    # Settings of xml config like "velocity" are automatically added.

  '''
  Controller initialization actions.
  '''
  def initialize(self):
    # hardware initialization
    for axis_name, axis in self.axes.iteritems():
      axis.settings.set('init_count', 0)
      # set initial speed
      axis.settings.set('velocity', axis.config.get("velocity", float))


  '''
  Axes initialization actions.
  '''
  def initialize_axis(self, axis):
    self._axis_moves[axis] = { "end_t": 0, "end_pos": random.randint(0,360) }

    # this is to test axis are initialized only once
    axis.settings.set('init_count', axis.settings.get('init_count')+1)

    # Add new axis oject method.
    add_axis_method(axis, self.get_identifier)


  '''
  Actions to perform at controller closing.
  '''
  def finalize(self):
    pass


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
  If new_position is passed, set the axis to this position.
  Always return the position (measured or desired) taken from controller 
  in steps.
  '''
  def position(self, axis, new_position=None, measured=False):
    if new_position is not None:
      self._axis_moves[axis]["end_pos"]=new_position
      self._axis_moves[axis]["end_t"]=0

    # Always return position
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
  If new_velocity is passed, set the axis velocity to this value.
  Always return the current velocity taken from controller 
  in steps/sec.
  '''
  def velocity(self, axis, new_velocity=None):
    if new_velocity is not None:
      axis.settings.set('velocity', new_velocity)

    # Always return velocity.
    return int(axis.settings.get('velocity'))


  '''
  If new_acctime is passed, set the axis acceleration time to this value.
  Always return the current acceleration time taken from controller 
  in seconds.
  '''
  def acctime(self, axis, new_acctime=None):
    if new_acctime is not None:
      axis.settings.set('acctime', new_acctime)

    # Always return acceleration time.
    return float(axis.settings.get('acctime'))


  '''
  '''
  def state(self, axis):
    if self._axis_moves[axis]["end_t"] > time.time():
      return MOVING
    else:
      self._axis_moves[axis]["end_t"]=0
      return READY


  '''
  Must send a command to the controller to abort the motion of given axis.
  '''
  def stop(self, axis):
    self._axis_moves[axis]["end_pos"] = self.position(axis)
    self._axis_moves[axis]["end_t"]   = 0


  '''
  Custom axis method returning the current name of the axis
  '''
  def get_identifier(self, axis):
    return axis.name
