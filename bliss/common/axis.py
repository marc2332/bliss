from bliss.common.task_utils import *
from bliss.config.motors.static import StaticConfig
import time

READY, MOVING, FAULT, UNKNOWN = ("READY", "MOVING", "FAULT", "UNKNOWN")


class Motion(object):
  def __init__(self, axis, target_pos, delta):
    self.__axis = axis
    self.target_pos = target_pos
    self.delta = delta
    self.backlash = 0

  @property
  def axis(self):
    return self.__axis


class Axis(object):
  class Settings:
    def set(*args, **kwargs):
      pass
    def get(*args, **kwargs):
      pass


  def __init__(self, name, controller, config):
    self.__name = name
    self.__controller = controller
    self.__config = StaticConfig(config)
    self.__settings = Axis.Settings()
    self.__move_done = gevent.event.Event()
    self.__move_done.set()


  @property
  def name(self):
    return self.__name


  @property
  def controller(self):
    return self.__controller


  @property
  def config(self):
    return self.__config


  @property
  def settings(self):
    return self.__settings


  @property
  def is_moving(self):
    return not self.__move_done.is_set()


  def has_tag(self, tag):
    for t, axis_list in self.__controller._tagged.iteritems():
      if t!=tag:
        continue
      if self.name in [axis.name for axis in axis_list]:
        return True
    return False


  def measured_position(self):
    return self.__controller.position(self, new_pos=None, measured=True)


  def step_size(self):
    return self.config.get("step_size", float, 1)


  def position(self, new_pos=None, measured=False):
    if self.is_moving:
      if new_pos is not None:
        raise RuntimeError("Can't set axis position while it is moving")
      return self.settings.get("position")
    else:
      pos = self._position(new_pos)
      if new_pos is not None:
        self.settings.set("position", pos)
      return pos


  def _position(self, new_pos=None, measured=False):
    return self.__controller.position(self, new_pos*self.step_size() if new_pos is not None else None, measured)/self.step_size()


  def state(self):
    if self.is_moving:
      return MOVING
    # really read from hw
    return self.__controller.state(self)


  def velocity(self, new_velocity=None):
    _vel = self.__controller.velocity(self, new_velocity)
    self.settings.set("velocity", _vel)
    return _vel


  def acctime(self, new_acctime=None):
    _acctime = self.__controller.acctime(self, new_acctime)
    self.settings.set("acctime", _acctime)
    return _acctime


  def _handle_move(self, motion):
    def update_settings():
       pos = self._position()
       self.settings.set("position", pos)
       state = self.__controller.state(self)
       self.settings.set("state", state)
       return state

    with cleanup(update_settings):
        while True:
          state = update_settings()
          if state != MOVING:
            break
          time.sleep(0.02)

        if motion.backlash:
          # axis has moved to target pos - backlash;
          # now do the final motion to reach original target
          final_pos = motion.target_pos + motion.backlash
          backlash_motion = Motion(self, final_pos, motion.backlash) 
          self.__controller.prepare_move(backlash_motion)
          self.__controller.start_one(backlash_motion)
          self._handle_move(backlash_motion)


  def prepare_move(self, user_target_pos, relative=False):
    initial_pos      = self.position()
    if relative:
      user_target_pos += initial_pos
    # all positions are converted to controller units
    backlash         = self.config.get("backlash", float, 0) * self.step_size()
    delta            = (user_target_pos - initial_pos) * self.step_size()
    target_pos       = user_target_pos * self.step_size()

    if backlash:
      if cmp(delta, 0) != cmp(backlash, 0):
        # move and backlash are not in the same direction;
        # apply backlash correction, the move will happen
        # in 2 steps
        target_pos -= backlash
        delta -= backlash
      else:
        # don't do backlash correction
        backlash = 0

    motion = Motion(self, target_pos, delta)
    motion.backlash = backlash
    self.__controller.prepare_move(motion)

    return motion


  def _set_move_done(self, move_task):
    self.__move_done.set()


  def move(self, user_target_pos, wait=True, relative=False):
    initial_state = self.state()
    if initial_state != READY:
      raise RuntimeError, "motor %s state is %r" % (self.name, initial_state)

    motion = self.prepare_move(user_target_pos, relative)

    self.__move_done.clear()

    move_task = self._do_move(motion, wait=False)
    move_task.link(self._set_move_done)

    if wait:
      move_task.get()
    else:
      return move_task


  @task
  def _do_move(self, motion, wait=True):
    with error_cleanup(self.stop):
      self.__controller.start_one(motion)

      self._handle_move(motion)

  def rmove(self, user_delta_pos, wait=True):
    return self.move(user_delta_pos, wait, relative=True)


  def wait_move(self):
    self.__move_done.wait()


  def stop(self):
    if self.is_moving:
       self.__controller.stop(self)
       self.wait_move()


class AxisRef(object):
  def __init__(self, name, _, config):
    self.__name = name
    self.__config = config
    self.settings = Axis.Settings()

  @property
  def name(self):
    return self.__name

  @property
  def config(self):
    return self.__config


class Group(object):
  def __init__(self, name, config):
    self.__name = name
    self.__config = StaticConfig(config)

  @property
  def name(self):
    return self.__name

  @property
  def config(self):
    return self.__config
