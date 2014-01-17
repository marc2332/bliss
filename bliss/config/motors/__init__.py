import sys
import os
from bliss.controllers.motor import Controller
from bliss.common.axis import Axis, Group

BACKEND = 'xml'

CONTROLLER_MODULES_PATH = [os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "controllers"))]
AXIS_MODULES_PATH = []

CONTROLLERS = {}
CONTROLLER_BY_AXIS = {} 
GROUPS = {}


def _get_module(module_name, path_list):
  try:
    module = sys.modules[module_name]
  except KeyError:
    old_syspath = sys.path[:]
    for path in path_list:
      sys.path.insert(0, path)

    try:
      return __import__(module_name, globals(), locals(), [""])
    finally:
      sys.path = old_syspath
  else:
    return module


def get_controller_class(controller_class_name, controller_modules_path=CONTROLLER_MODULES_PATH):
  controller_module = _get_module(controller_class_name, controller_modules_path)

  try:
    controller_class = getattr(controller_module, controller_class_name)
  except:
    try:
      controller_class = getattr(controller_module, controller_class_name.title())
    except:
      raise RuntimeError("could not find class '%s` in module '%s`" % (controller_class_name, controller_module))

  return controller_class


def get_axis_class(axis_class_name, axis_modules_path=AXIS_MODULES_PATH):
  axis_module = _get_module(axis_class, axis_modules_path)

  try:
    axis_class = getattr(axis_module, axis_class_name)
  except:
    raise RuntimeError("could not find class '%s` in module '%s`" % (axis_class_name, axis_module))
  else:
    return axis_class 


def add_controller(controller_name, controller_config, controller_class, controller_axes):
  global CONTROLLERS
  global CONTROLLER_BY_AXIS

  if controller_name in CONTROLLERS:
    CONTROLLERS[controller_name]["object"].finalize()
    del CONTROLLERS[controller_name]

  axes = []
  for axis_name, axis_class_name, axis_config in controller_axes:
    if axis_class_name is None:
      axis_class = Axis
    else:
      axis_class = get_axis_class(axis_class_name)
    axes.append((axis_name, axis_class, axis_config))
    CONTROLLER_BY_AXIS[axis_name]=controller_name

  CONTROLLERS[controller_name] = { "object": controller_class(controller_name, controller_config, axes),
                                   "initialized": False }


def add_group(group_name, group_config, group_class=Group):
  global GROUPS
  GROUPS[group_name] = { "object": group_class(group_name, group_config) }


def get_axis(axis_name):
    try:
      controller_name = CONTROLLER_BY_AXIS[axis_name]
    except KeyError:
      raise RuntimeError("no axis '%s` in config" % axis_name)
    else:
      try:
        controller = CONTROLLERS[controller_name]
      except KeyError:
        raise RuntimeError("no controller can be found for axis '%s`" % axis_name)

    try:
      controller_instance = controller["object"]
    except KeyError:
      raise RuntimeError("could not get controller for axis '%s`" % axis_name)
    
    if not controller["initialized"]:
      controller_instance.initialize()
      controller["initialized"] = True

    axis = controller_instance.get_axis(axis_name)

    return axis


def get_group(group_name):
  try:
    group = GROUPS[group_name]
  except KeyError:
    raise RuntimeError("no group '%s` in config" % group_name)

  return group["object"]


def load_cfg(filename):
  if BACKEND == 'xml':
    from bliss.config.motors.xml_backend import load_cfg
    return load_cfg(filename)


def load_cfg_fromstring(config_str):
  if BACKEND == 'xml':
    from bliss.config.motors.xml_backend import load_cfg_fromstring
    return load_cfg_fromstring(config_str)
