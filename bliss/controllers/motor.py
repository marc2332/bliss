import types
import gevent
import gevent.event
import functools
from bliss.config.motors.static import StaticConfig
from bliss.common.task_utils import task
from bliss.controllers.motor_settings import AxisSettings
from bliss.common.axis import AxisRef, MOVING, READY, FAULT, UNKNOWN
from bliss.config.motors import get_axis
from bliss.common import event


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
    self._tagged = dict()

    self.axis_settings = AxisSettings()

    for axis_name, axis_class, axis_config in axes:
        axis = axis_class(axis_name, self, axis_config)
        self._axes[axis_name] = axis
        axis_tags = axis_config.get('tags')
        if axis_tags:
          for tag in axis_tags.split():
            self._tagged.setdefault(tag, []).append(axis) #_name)
        self.__initialized_axis[axis] = False

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

  def _update_refs(self):
    for axis in self.axes.itervalues():
      if not isinstance(axis, AxisRef):
        continue 
      referenced_axis = get_axis(axis.name)
      self.axes[axis.name]=referenced_axis
      self.__initialized_axis[referenced_axis] = True
      for tag, axis_list in self._tagged.iteritems():
        try:
          i = axis_list.index(axis)
        except ValueError:
          continue 
        else:
          axis_list[i] = referenced_axis
          referenced_axis.controller._tagged.setdefault(tag,[]).append(referenced_axis)
      

  def initialize(self):
    pass

  def finalize(self):
    pass

  def get_axis(self, axis_name):
    axis = self._axes[axis_name]

    if not self.__initialized_axis[axis]:
      self.initialize_axis(axis)
      self.__initialized_axis[axis] = True

      # Handle optional operation parameters from config
      try:
        axis.velocity(axis.config.get("velocity"))
      except:
        pass

      # Handle optional operation parameters from config
      try:
        axis.acctime(axis.config.get("acctime"))
      except:
        pass

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

  def state(self, axis):
    raise NotImplementedError

  def acctime(self, axis, new_acctime=None):
    raise NotImplementedError


class CalcController(Controller):
  def __init__(self, *args, **kwargs):
    Controller.__init__(self, *args, **kwargs)
  
  def _update_refs(self):
    Controller._update_refs(self)
 
    self.reals = []
    for real_axis in self._tagged['real']:
      self.reals.append(real_axis)
      event.connect(real_axis, 'position', self._calc_from_real)
      event.connect(real_axis, 'state', self._update_state_from_real)
    self.pseudos = [axis for axis_name, axis in self.axes.iteritems() if axis not in self.reals]

  def _calc_from_real(self, *args, **kwargs):
    real_positions = dict()
    for tag, axis_list in self._tagged.iteritems():
      if len(axis_list) > 1:
        continue
      axis = axis_list[0]
      if axis in self.reals:
        real_positions[tag] = axis.position()

    new_positions = self.calc_from_real(real_positions)

    for tagged_axis_name, position in new_positions.iteritems():
      axis = self._tagged[tagged_axis_name][0]
      if axis in self.pseudos:
        self.position(axis, position)
      else:
        raise RuntimeError("cannot assign position to real motor")

  def calc_from_real(self, real_positions):
    """Return a dict { pseudo motor tag: new position, ... }"""
    raise NotImplementedError

  def _update_state_from_real(self, *args, **kwargs):
    real_states = list()
    for tag, axis_list in self._tagged.iteritems():
      if len(axis_list) > 1:
        continue
      axis = axis_list[0]
      if axis in self.reals:
        real_states.append(axis.state())

    if any([state == MOVING for state in real_states]):
      for axis in self.pseudos:
        self.state(axis, MOVING)   
    elif all([state == READY for state in real_states]):
      for axis in self.pseudos:
        self.state(axis, READY)
    else:
      self.state(axis, FAULT) 

  def initialize_axis(self, axis):
    if axis in self.pseudos:
        self._calc_from_real()
        self._update_state_from_real()

  def prepare_move(self, axis, target_pos, delta):
    pass

  def start_move(self, axis, target_pos, delta):
    pass

  def stop(self, axis):
    [axis.stop() for axis in self.reals]

  def position(self, axis, new_pos=None, measured=False):
    if new_pos is not None:
      axis.settings.set('position', new_pos)
    else:
      return axis.settings.get('position')

  def velocity(self, axis, new_velocity=None):
    pass

  def state(self, axis, new_state=None):
    if new_state is not None:
      axis.settings.set('state', new_state)
    else:
      return axis.settings.get('state')
