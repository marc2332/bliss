from bliss.common.task_utils import *
from bliss.config.motors.static import StaticConfig
import time

READY, MOVING, FAULT, UNKNOWN = ("READY", "MOVING", "FAULT", "UNKNOWN")

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


  def measured_position(self):
    return self.__controller.position(self, new_pos=None, measured=True)


  def step_size(self):
    return self.config.get("step_size", float, 1)


  def position(self, new_pos=None, measured=False):
    if self.is_moving:
      if new_pos is not None:
        raise RuntimeError("Can't set axis position while it is moving")
      return self.__settings.get("position")
    else:
      if new_pos is not None:
        self._position(new_pos)
        self.settings.set("position", new_pos)
      else:
        # really read from hw
        return self._position()


  def _position(self, new_pos=None, measured=False):
    if new_pos is None:
      return self.__controller.position(self, new_pos, measured)/self.step_size()
    else:
      self.__controller.position(self, new_pos*self.step_size())


  def state(self):
    if self.is_moving:
      return MOVING
    # really read from hw
    return self.__controller.state(self)


  def velocity(self, new_velocity=None):
    return self.__controller.velocity(self, new_velocity)


  def acctime(self, new_acctime=None):
    return self.__controller.acctime(self, new_acctime)


  def _handle_move(self, target_pos, delta, backlash=0):
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

        if backlash:
          # axis has moved to target pos - backlash;
          # now do the final motion to reach original target
          final_pos = target_pos + backlash
          self.__controller.prepare_move(self, final_pos, backlash)
          self.__controller.start_move(self, final_pos, backlash)
          self._handle_move(final_pos, backlash)


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
    
    self.__controller.prepare_move(self, target_pos, delta)

    return target_pos, delta, backlash


  def _set_move_done(self, move_task):
    self.__move_done.set()


  def move(self, user_target_pos, wait=True, relative=False):
    initial_state = self.state()
    if initial_state != READY:
      raise RuntimeError, "motor %s state is %r" % (self.name, initial_state)

    target_pos, delta, backlash = self.prepare_move(user_target_pos, relative)

    self.__move_done.clear()

    move_task = self._do_move(target_pos, delta, backlash, wait=False)
    move_task.link(self._set_move_done)

    if wait:
      move_task.get()
    else:
      return move_task


  @task
  def _do_move(self, target_pos, delta, backlash, wait=True):
    with error_cleanup(self.stop):
      self.__controller.start_move(self, target_pos, delta)

      self._handle_move(target_pos, delta, backlash)

 
  def rmove(self, user_delta_pos, wait=True):
    return self.move(user_delta_pos, wait, relative=True)


  def wait_move(self):
    self.__move_done.wait()


  def stop(self):
    if self.is_moving:
       self.__controller.stop(self)
       self.wait_move()


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
