import gevent
import gevent.event
import functools
from bliss.common.task_utils import task
from bliss.controllers.motor_settings import AxisSettings
from bliss.common.axis import MOVING, READY
from bliss.common import event

class Controller:
  def __init__(self, name, config, axes):
    self.__name = name
    self.__config = config
    self.__initialized_axis = dict()
    self._axes = dict()
    self._move_tasks = dict()
    self._is_moving = dict()

    self.axis_settings = AxisSettings()
    self.axis_settings.state_updated_callback = self.state_changed_event

    for axis_name, axis_class, axis_config in axes:
        axis = axis_class(self, axis_config)
        self._axes[axis_name] = axis
        self._is_moving[axis] = gevent.event.Event()
        self.__initialized_axis[axis] = False
 
        # push config from XML file into axes settings.
        self.axis_settings.set_from_config(axis, axis.config)

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

  def get_axis(self, axis_name):
    axis = self._axes[axis_name]

    if not self.__initialized_axis[axis]:
      self.initialize_axis(axis)
      self.__initialized_axis[axis] = True

    return axis

  def initialize_axis(self, axis):
    raise NotImplementedError

  def state_changed_event(self, axis, new_state):
    event = self._is_moving[axis]
    if new_state == MOVING:
      event.set()
    else:
      event.clear()

  def prepare_move(self, axis, target_pos):
    if self._move_tasks.get(axis) and not self._move_tasks[axis].ready():
      raise RuntimeError("axis '%s` is busy" % axis)
    self._move_tasks[axis] = self._move(axis,
                                        target_pos,
                                        target_pos-self.read_position(axis),
                                        start=False)

  def start_move(self):
    for axis, move_task in self._move_tasks.iteritems():
      move_task.link(lambda _: self._move_tasks.pop(axis))
      move_task.start()

  @task
  def _move(self, axis, target_pos, delta):
    raise NotImplementedError

  def wait_is_moving(self, axis):
    self._is_moving[axis].wait()

  def wait(self):
    return gevent.wait(self._move_tasks.values())

  def abort(self, axis):
    move_task = self._move_tasks.get(axis)
    if move_task:
      move_task.kill()

  def update_position(self, axis, position):
    self._update(axis, "position", position)

  def update_state(self, axis, state):
    self._update(axis, "state", state)

  def _update(self, axis, setting_name, value):
    self.axis_settings.set(axis, setting_name, value)
    event.send(axis, setting_name, self.axis_settings.get(axis, setting_name))

  def read_position(self, axis, measured=False):
    raise NotImplementedError

  def read_velocity(self, axis):
    raise NotImplementedError

  def read_state(self, axis):
    raise NotImplementedError


