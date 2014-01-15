from bliss.common.task_utils import *

READY, MOVING = ("READY", "MOVING")


class Axis:
  class Settings:
    def set(*args, **kwargs):
      pass
    def get(*args, **kwargs):
      pass

  def __init__(self, controller, config):
    self.__controller = controller
    self.__config = config
    self.__settings = Axis.Settings()

  @property
  def controller(self):
    return self.__controller

  @property
  def config(self):
    return self.__config

  @property
  def settings(self):
    return self.__settings

  def position(self, measured=False):
    return self.__controller.read_position(self, measured)

  def velocity(self):
    return self.__controller.read_velocity(self)
 
  def state(self):
    return self.__controller.read_state(self)

  def move(self, target_pos, wait=True):
    self.__controller.prepare_move(self, target_pos)
    self.__controller.start_move()
    self.__controller.wait_is_moving(self)

    if wait: 
      self.__controller.wait()
    else:
      return gevent.spawn(self.__controller.wait)

class Group:
  def __init__(self, name, config):
    self.__name = name

  @property
  def name(self):
    return self.__name


