from bliss.common.task_utils import *
from bliss.common import event
import functools
import time

READY, MOVING = ("READY", "MOVING")

class Axis:
  class Settings:
    def set(*args, **kwargs):
      pass
    def get(*args, **kwargs):
      pass

  def __init__(self, name, controller, config):
    self.__name = name
    self.__controller = controller
    self.__config = config
    self.__settings = Axis.Settings()
    self.__move_task = None

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

  def measured_position(self):
    return self.__controller.read_position(self, measured=True)

  def is_moving(self):
    return self.__move_task is not None and not self.__move_task.ready()

  def position(self):
    if self.is_moving():
      return self.__settings.get("position")
    # really read from hw
    return self.__controller.read_position(self)

  def state(self):
    if self.is_moving():
      return MOVING
    # really read from hw
    return self.__controller.read_state(self)

  def velocity(self):
    return self.__controller.read_velocity(self)

  def _handle_move(self):
    def update_settings():
       pos = self.__controller.read_position(self)
       self.settings.set("position", pos)
       event.send(self, "position", pos) 
       state = self.__controller.read_state(self)
       self.settings.set("state", state)
       event.send(self, "state", state)
       return state

    with cleanup(update_settings):
      with error_cleanup(functools.partial(self.__controller.stop, self)):
        while True: 
          state = update_settings()
          if state != MOVING:
            break
          time.sleep(0.02)
       
  def prepare_move(self, target_pos):
    initial_state = self.state()
    if initial_state != READY:
      raise RuntimeError, "motor %s state is %r" % (self.name, initial_state)

    initial_pos      = self.position()
    delta            = target_pos - initial_pos
    self.__controller.prepare_move(self, target_pos, delta)
    return initial_pos, target_pos, delta
 
  def move(self, target_pos, wait=True):
    initial_pos, target_pos, delta = self.prepare_move(target_pos)

    self.__controller.start_move(self, target_pos, delta)
    
    self.__move_task = gevent.spawn(self._handle_move)

    if wait: 
      self.__move_task.get()
    else:
      return self.__move_task

  def stop(self):
    if self.is_moving():
       self.__controller.stop(self)
       self.__move_task.join()


class Group:
  def __init__(self, name, config):
    self.__name = name

  @property
  def name(self):
    return self.__name


