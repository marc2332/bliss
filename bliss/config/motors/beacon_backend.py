from bliss.config import static
from bliss.config import settings
from bliss.config import channels
from bliss.common import event
from . import get_controller_class, get_axis_class, add_controller, set_backend, Axis, AxisRef, CONTROLLER_BY_AXIS, write_setting as config_write_setting
import functools
import gevent

def create_objects_from_config_node(config, node):
    set_backend("beacon")

    name = node.get('name')
    controller_config = node.parent
   
    controller_class_name = controller_config.get('class')
    controller_name = controller_config.get('name')
    if controller_name is None:
            controller_name = "%s_%d" % (
                controller_class_name, id(controller_config))

    controller_class = get_controller_class(controller_class_name)
    axes = list()
    axes_names = list()
    for axis_config in controller_config.get('axes'):
        axis_name = axis_config.get("name")
        CONTROLLER_BY_AXIS[axis_name] = controller_name
	if axis_name.startswith("$"):
	    axis_class = AxisRef
	    axis_name = axis_name.lstrip('$')
	else:
	    axis_class_name = axis_config.get("class")
	    if axis_class_name is None:
		axis_class = Axis
	    else:
		axis_class = get_axis_class(axis_class_name)
            if axis_name != name:
                axes_names.append(axis_name)
        axes.append((axis_name, axis_class, axis_config))
        #static.register_motor(axis_name)

    controller = controller_class(controller_name, controller_config, axes, [])
    controller._update_refs()
    controller.initialize()
    axis = controller.get_axis(name)
    event.connect(axis, "write_setting", config_write_setting)

    cache_dict = dict(zip(axes_names, [controller]*len(axes_names)))
    return {name: axis}, cache_dict    

def create_object_from_cache(config, name, controller):
    axis = controller.get_axis(name)
    event.connect(axis, "write_setting", config_write_setting)
    return axis

def load_cfg_fromstring(config_yaml):
    """Load configuration from yaml string

    Args:
        config_yaml (str): string holding yaml representation of config

    Returns:
        None
    """
    yaml_doc = static.load_cfg_fromstring(config_yaml)
    _load_config(yaml_doc)


def load_cfg(config_file):
    """Load configuration from yaml file

    Args:
        config_file (str): full path to configuration file

    Returns:
        None
    """
    yaml_doc = static.load_cfg(config_file)
    _load_config(yaml_doc)


def _load_config(config_tree):
    for controller_config in config_tree["controllers"]:
        controller_name = controller_config.get("name")
        controller_class_name = controller_config.get("class")
        if controller_name is None:
            controller_name = "%s_%d" % (
                controller_class_name, id(controller_config))

        controller_class = get_controller_class(controller_class_name)

        config = controller_config

        add_controller(
            controller_name,
            config,
            load_axes(controller_config),
            controller_class)

    for group_node in config_tree.get("groups",[]):
        group_name = group_node.get('name')
        if group_name is None:
            raise RuntimeError("%s: group with no name" % group_node)
        config = group_node

        add_group(group_name, config, load_axes(group_node))


def load_axes(config_node):
    """Return list of (axis name, axis_class_name, axis_config_node)"""
    axes = []
    for axis_config in config_node['axes']:
        axis_name = axis_config.get("name")
        if axis_name is None:
            raise RuntimeError(
                "%s: configuration for axis does not have a name" %
                config_node)
        axis_class_name = axis_config.get("class")
        config = axis_config
        axes.append((axis_name, axis_class_name, config))
    return axes


def write_setting(config_dict, setting_name, setting_value):
    axis_name = config_dict["name"]
    
    hash_setting = settings.HashSetting("axis.%s" % axis_name)
    hash_setting[setting_name] = setting_value

    print 'writing', setting_name, setting_value
    channels.Channel("axis.%s.%s" % (axis_name, setting_name), setting_value)


def commit_settings(config_dict):
    return 


def setting_update_from_channel(value, setting_name=None, axis=None):
    print 'callback from channel', value, setting_name, axis
    axis.settings.set(setting_name, value, write=False, from_channel=True)


def get_axis_setting(axis, setting_name):
    hash_setting = settings.HashSetting("axis.%s" % axis.name)
    if len(hash_setting) == 0:
      try:
          setting_value = axis.config.get(setting_name)
      except:
          return None
      else:
          # write setting
          hash_setting[setting_name] = setting_value
    else:
        setting_value = hash_setting.get(setting_name)

    if not hasattr(axis, "_beacon_channels"):
        axis._beacon_channels = dict()
    #if setting_name in axis._beacon_channels:
    #    axis._beacon_channels[setting_name].value = setting_value
    if not setting_name in axis._beacon_channels:
        chan_name = "axis.%s.%s" % (axis.name, setting_name)
        cb = functools.partial(setting_update_from_channel, setting_name=setting_name, axis=axis) 
        chan = channels.Channel(chan_name, setting_value, callback=cb)
        axis._beacon_channels[setting_name] = chan
        #axis._beacon_channels.setdefault("callbacks", dict())[setting_name] = cb
    
    return setting_value


class StaticConfig(object):

    def __init__(self, config_dict):
        self.config_dict = config_dict

    def get(self, property_name, converter=str, default=None):
        """Get static property

        Args:
            property_name (str): Property name
            converter (function): Default :func:`str`, Conversion function from configuration format to Python
            default: Default: None, default value for property

        Returns:
            Property value

        Raises:
            KeyError, ValueError
        """
        property_value = self.config_dict.get(property_name)
        if property_value is not None:
            return converter(property_value)
        else:
            if default is not None:
                return default

            raise KeyError("no property '%s` in config" % property_name)

