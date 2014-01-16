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
    self.get_property("host")

    # Add a "channel" paramter to axes.
    # Check that <channel> is really an integer.
    self.axis_settings.add('channel', int)
    self.axis_settings.add('init_count', int)

  def initialize(self):
    # hardware initialization
    for axis_name, axis in self.axes.iteritems():
      axis.settings.set('init_count', 0)

  def initialize_axis(self, axis):
    axis.settings.set('position', random.randint(0,360))
    self._axis_moves[axis] = { "end_t": 0, "end_pos": axis.settings.get('position') }

    # this is to test axis are initialized only once
    axis.settings.set('init_count', axis.settings.get('init_count')+1)

  def prepare_move(self, axis, target_pos, delta):
    pos = self.read_position(axis)
    self._axis_moves[axis] = { "start_pos": pos,
                               "delta": delta,
                               "end_pos": target_pos }

  def start_move(self, axis):
    v = self.read_velocity(axis)
    t0 = time.time()
    delta = self._axis_moves[axis]["delta"]
    d = math.copysign(1, delta)
    end_t = t0 + math.fabs(delta/float(v))
    self._axis_moves[axis].update({ "end_t": end_t, "t0": t0 })

  def read_position(self, axis, measured=False):
    if self._axis_moves[axis]["end_t"]:
      # motor is moving
      t = time.time()
      v = self.read_velocity(axis)
      d = math.copysign(1, self._axis_moves[axis]["delta"])
      dt = t - self._axis_moves[axis]["t0"]
      pos = self._axis_moves[axis]["start_pos"] + d*dt*v
      return pos
    else:
      return self._axis_moves[axis]["end_pos"]

  def read_velocity(self, axis):
    return axis.settings.get('velocity')

  def read_state(self, axis):
    if self._axis_moves[axis]["end_t"] > time.time():
      return MOVING
    else:
      return READY

  def stop(self, axis):
    print 'stop is called'
    self._axis_moves[axis]["end_t"]=0
