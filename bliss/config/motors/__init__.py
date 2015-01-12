
import sys
import os
from bliss.common import event
from bliss.common.axis import Axis, AxisRef
from bliss.controllers.motor_group import Group
try:
    from bliss.config.static import get_config as beacon_get_config
except ImportError:
    def beacon_get_config(*args):
        raise RuntimeError("Beacon is not imported")

BEACON_CONFIG = None

BACKEND = 'xml'

CONTROLLER_MODULES_PATH = [
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..","controllers","motors"))]
AXIS_MODULES_PATH = []

CONTROLLERS = {}
CONTROLLER_BY_AXIS = {}
LOADED_FILES = set()

def set_backend(backend):
    global BACKEND
    if not BACKEND in ("xml", "beacon"):
        raise RuntimeError("Unknown backend '%s`" % backend)
    BACKEND = backend

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


def get_controller_class(
        controller_class_name,
        controller_modules_path=CONTROLLER_MODULES_PATH):
    """Get controller class object from controller class name

    Args:
        controller_class_name (str):
            The controller class name.
        controller_modules_path (list):
            Default CONTROLLER_MODULES_PATH;
            List of paths to look modules for.

    Returns:
        Controller class object

    Raises:
        RuntimeError
    """
    controller_module = _get_module(
        controller_class_name,
        controller_modules_path)
    try:
        controller_class = getattr(controller_module, controller_class_name)
    except:
        try:
            controller_class = getattr(
                controller_module,
                controller_class_name.title())
        except:
            raise RuntimeError(
                "could not find class '%s` in module '%s`" %
                (controller_class_name, controller_module))

    return controller_class


def get_axis_class(axis_class_name, axis_modules_path=AXIS_MODULES_PATH):
    """Get axis class object from axis class name

    Args:
        axis_class_name (str):
            The axis class name
        axis_modules_path (list):
            Default AXIS_MODULES_PATH;
            List of paths to look modules for

    Returns:
        Axis class object

    Raises:
        RuntimeError
    """
    axis_module = _get_module(axis_class_name, axis_modules_path)

    try:
        axis_class = getattr(axis_module, axis_class_name)
    except:
        raise RuntimeError(
            "could not find class '%s` in module '%s`" %
            (axis_class_name, axis_module))
    else:
        return axis_class


def add_controller(
        controller_name,
        controller_config,
        controller_axes,
        controller_class):
    """Instanciate a controller object from configuration, and store it in the global CONTROLLERS dictionary

    Args:
        controller_name (str):
            Controller name, has to be unique
        controller_config (dict):
            Dictionary containing the configuration of the controller
        controller_axes (list):
            A list of tuples (axis_name, axis_class_name, axis_config) for each axis in controller
        controller_class (class object):
            Controller class

    Returns:
        None
    """
    axes = list()
    for axis_name, axis_class_name, axis_config in controller_axes:
        if not CONTROLLER_BY_AXIS.get(axis_name):
            # new axis
            CONTROLLER_BY_AXIS[axis_name] = controller_name

            if axis_class_name is None:
                axis_class = Axis
            else:
                axis_class = get_axis_class(axis_class_name)

            axes.append((axis_name, axis_class, axis_config))
        else:
            # existing axis
            # the next test is to check if the class is a CalcController without importing the module...
            if any(['CalcController' in base_class_name for base_class_name in map(str, controller_class.__bases__)]):
                axes.append((axis_name, AxisRef, axis_config))
            else:
                raise RuntimeError("Duplicated axis in config: %r" % axis_name)

    controller = controller_class(controller_name, controller_config, axes)
    CONTROLLERS[controller_name] = {"object": controller,
                                    "initialized": False}


def get_axis(axis_name):
    """Get axis from loaded configuration or from Beacon

    If needed, instanciates the controller of the axis and initializes it.

    Args:
        axis_name (str):
            Axis name

    Returns:
        :class:`bliss.common.axis.Axis` object

    Raises:
        RuntimeError
    """
    if BACKEND=='beacon':
        global BEACON_CONFIG
        if BEACON_CONFIG is None:
            BEACON_CONFIG = beacon_get_config() 
        o = BEACON_CONFIG.get(axis_name)
        if not isinstance(o, Axis):
            raise AttributeError("'%s` is not an axis" % axis_name)
	event.connect(o, "write_setting", write_setting)
        return o
 
    try:
        controller_name = CONTROLLER_BY_AXIS[axis_name]
    except KeyError:
        raise RuntimeError("no axis '%s` in config" % axis_name)
    else:
        try:
            controller = CONTROLLERS[controller_name]
        except KeyError:
            raise RuntimeError(
                "no controller can be found for axis '%s`" %
                axis_name)

    try:
        controller_instance = controller["object"]
    except KeyError:
        raise RuntimeError(
            "could not get controller instance for axis '%s`" %
            axis_name)

    if not controller["initialized"]:
        controller_instance._update_refs()
        controller_instance.initialize()
        controller["initialized"] = True

    axis = controller_instance.get_axis(axis_name)
    event.connect(axis, "write_setting", write_setting)

    return axis


def axis_names_list():
    """Return list of all Axis objects names in loaded configuration"""
    return CONTROLLER_BY_AXIS.keys()


def clear_cfg():
    """Clear configuration

    Remove all controllers; :func:`bliss.controllers.motor.finalize` is called on each one.
    """
    if BACKEND == 'beacon':
        global BEACON_CONFIG
        if BEACON_CONFIG is not None:
            BEACON_CONFIG._clear_instances()
    else:
        global CONTROLLERS
        global CONTROLLER_BY_AXIS
        global LOADED_FILES

        for controller_name, controller in CONTROLLERS.iteritems():
             controller["object"].finalize()
        CONTROLLERS = {}
        CONTROLLER_BY_AXIS = {}
        LOADED_FILES = set()


def load_cfg(filename, clear=True):
    """Load configuration from file

    Configuration is cleared first (calls :func:`clear_cfg`)
    Calls the right function depending on the current backend set by the
    BACKEND global variable. Defaults to 'xml'.

    Args:
        filename (str):
            Full path to configuration file

    Returns:
        None
    """

    if clear:
        clear_cfg()
    if filename in LOADED_FILES:
        return
    if BACKEND == 'xml':
        filename = os.path.abspath(filename)
        from bliss.config.motors.xml_backend import load_cfg
    elif BACKEND == 'beacon':
        from bliss.config.motors.beacon_backend import load_cfg
    try:
        load_cfg(filename)
    except:
        raise
    else:
        LOADED_FILES.add(filename)


def load_cfg_fromstring(config_str, clear=True):
    """Load configuration from string

    Configuration is cleared first (calls :func:`clear_cfg`)
    Calls the right function depending on the current backend set by the
    BACKEND global variable. Defaults to 'xml'.

    Args:
        config_str (str):
            Configuration string

    Returns:
        None
    """
    if clear:
        clear_cfg()
    if BACKEND == 'xml':
        from bliss.config.motors.xml_backend import load_cfg_fromstring
    elif BACKEND == 'beacon':
        from bliss.config.motors.beacon_backend import load_cfg_fromstring
    return load_cfg_fromstring(config_str)


def write_setting(axis_config, setting_name, setting_value, commit=True):
    if BACKEND == 'xml':
        from bliss.config.motors.xml_backend import write_setting
    elif BACKEND == 'beacon':
        from bliss.config.motors.beacon_backend import write_setting

    write_setting(
        axis_config.config_dict, setting_name, setting_value)
    if commit:
        commit_settings(axis_config)

def commit_settings(axis_config):
    if BACKEND == 'xml':
        from bliss.config.motors.xml_backend import commit_settings
    elif BACKEND == 'beacon':
        from bliss.config.motors.beacon_backend import commit_settings
    commit_settings(axis_config.config_dict)

def get_axis_setting(axis, setting_name):
    """Get setting value from axis and setting name

    Args:
        axis:
           Axis object (Axis object)
        
        setting_name (str):
            Setting name

    Returns:
        Setting value, or None if setting has never been set

    Raises:
        RuntimeError if settings does not exist for axis 
    """
    if BACKEND == 'xml':
        try:
            setting_value = axis.config.config_dict["settings"].get(setting_name)
        except KeyError:
            raise RuntimeError
        else:
            return setting_value["value"] if setting_value else None
    elif BACKEND == 'beacon':
        from bliss.config.motors.beacon_backend import get_axis_setting
        return get_axis_setting(axis, setting_name)


def StaticConfig(*args, **kwargs):
    if BACKEND == 'xml':
      from bliss.config.motors.xml_backend import StaticConfig
      return StaticConfig(*args, **kwargs)  
    elif BACKEND == 'beacon':
      from bliss.config.motors.beacon_backend import StaticConfig
      return StaticConfig(*args, **kwargs)  
