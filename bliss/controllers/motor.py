import types
import gevent
import gevent.event
import functools
from bliss.config.motors.static import StaticConfig
from bliss.common.task_utils import task
from bliss.controllers.motor_settings import AxisSettings
from bliss.common.axis import MOVING, READY, UNKNOWN


def add_axis_method(axis_object, method, name=None, args=[]):
     if name is None:
         name = method.im_func.func_name
     def call(self, *args, **kwargs):
	 return method.im_func(method.im_self, *args, **kwargs)
     setattr(axis_object, name, types.MethodType(functools.partial(call, *([axis_object]+args)), axis_object))


class Controller(object):
  def __init__(self, name, config, axes):
    self.__name = name
    self.__config = StaticConfig(config)
    self.__initialized_axis = dict()
    self._axes = dict()

    self.axis_settings = AxisSettings()

    for axis_name, axis_class, axis_config in axes:
        axis = axis_class(axis_name, self, axis_config)
        self._axes[axis_name] = axis
        self.__initialized_axis[axis] = False

        # push config from XML file into axes settings.
        #self.axis_settings.set_from_config(axis, axis.config)

        # install axis.settings set/get methods
        axis.settings.set = functools.partial(self.axis_settings.set, axis)
        axis.settings.get = functools.partial(self.axis_settings.get, axis)

  @property
  def axes(self):
    return self._axes

  @property
  def name(self):
    return self.__name

  @property
  def config(self):
    return self.__config

  def finalize(self):
    pass

  def get_axis(self, axis_name):
    axis = self._axes[axis_name]

    if not self.__initialized_axis[axis]:
      self.initialize_axis(axis)
      self.__initialized_axis[axis] = True

    return axis

  def initialize_axis(self, axis):
    raise NotImplementedError

  def prepare_move(self, axis, target_pos, delta):
    return

  def start_move(self, axis, target_pos, delta):
    raise NotImplementedError

  def stop(self, axis):
    raise NotImplementedError

  def position(self, axis, new_pos=None, measured=False):
    raise NotImplementedError

  def velocity(self, axis, new_velocity=None):
    raise NotImplementedError

  def acctime(self, axis, new_acctime=None):
    raise NotImplementedError

  def read_state(self, axis):
    raise NotImplementedError


