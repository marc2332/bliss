# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import static
from bliss.config import settings
from bliss.config import channels
from bliss.common import event
from bliss.common.utils import Null
from . import get_controller_class, get_axis_class, get_encoder_class, add_controller, set_backend, Axis, AxisRef, CONTROLLER_BY_AXIS, Encoder, CONTROLLER_BY_ENCODER
from . import write_setting as config_write_setting
import functools
import gevent


def create_objects_from_config_node(config, node):
    set_backend("beacon")

    if 'axes' in node or 'encoders' in node:
        # asking for a controller
        create = __create_controller_from_config_node
    else:
        # asking for an axis (controller is the parent)
        create = __create_axis_from_config_node
    return create(config, node)


def __create_controller_from_config_node(config, node):
    controller_class_name = node.get('class')
    controller_name = node.get('name', '%s_%d' % (node.get('class'), id(node)))
    controller_class = get_controller_class(controller_class_name)
    axes = list()
    axes_names = list()
    encoders = list()
    encoder_names = list()
    for axis_config in node.get('axes'):
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
            axes_names.append(axis_name)
        axes.append((axis_name, axis_class, axis_config))
    for encoder_config in node.get('encoders', []):
        encoder_name = encoder_config.get("name")
        CONTROLLER_BY_ENCODER[encoder_name] = controller_name
        encoder_class_name = encoder_config.get("class")
        if encoder_class_name is None:
            encoder_class = Encoder
        else:
            encoder_class = get_encoder_class(encoder_class_name)
        encoder_names.append(encoder_name)
        encoders.append((encoder_name, encoder_class, encoder_config))

    controller = controller_class(controller_name, node, axes, encoders)
    controller._update_refs()
    controller.initialize()
    all_names = axes_names + encoder_names
    cache_dict = dict(zip(all_names, [controller]*len(all_names)))
    return {controller_name: controller}, cache_dict


def __create_axis_from_config_node(config, node):
    name = node.get('name')
    objs, cache = __create_controller_from_config_node(config, node.parent)
    controller = cache.pop(name)
    objs[name] = create_object_from_cache(config, name, controller)
    return objs, cache


def create_object_from_cache(config, name, controller):
    try:
        o = controller.get_axis(name)
    except KeyError:
        o = controller.get_encoder(name) 
    else:
        event.connect(o, "write_setting", config_write_setting)
    
    return o

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


def write_setting(config_dict, setting_name, setting_value, write):
    axis_name = config_dict["name"]
    #print 'in write_setting', axis_name, setting_name, str(setting_value)
 
    if write:
       channels.Channel("axis.%s.%s" % (axis_name, setting_name), setting_value)
       if setting_name not in ('state', 'position'):
           hash_setting = settings.HashSetting("axis.%s" % axis_name)
           hash_setting[setting_name] = setting_value


def setting_update_from_channel(value, setting_name=None, axis=None):
    if axis._hw_control:
        return

    axis.settings.set(setting_name, value, write=False, from_channel=True)
 
    #print 'setting update from channel', axis.name, setting_name, str(value)

    if setting_name == 'state':
        if 'MOVING' in str(value):
            axis._set_moving_state(from_channel=True)
        else:
            if axis.is_moving:
                axis._set_move_done(None)


def get_from_config(axis, setting_name):
    try:
        return axis.config.get(setting_name)
    except KeyError:
        return


def get_axis_setting(axis, setting_name):
    hash_setting = settings.HashSetting("axis.%s" % axis.name)
    if len(hash_setting) == 0:
        # there is no setting value in cache
        setting_value = get_from_config(axis, setting_name)
        if setting_value is not None:
            # write setting to cache
            hash_setting[setting_name] = setting_value
    else:
        setting_value = hash_setting.get(setting_name)
        if setting_value is None:
            # take setting value from config
            setting_value = get_from_config(axis, setting_name)
            if setting_value is not None:
                # write setting to cache
                hash_setting[setting_name] = setting_value

    try:
        beacon_channels = axis._beacon_channels
    except AttributeError:
        beacon_channels = dict()
        axis._beacon_channels = beacon_channels
    
    if not setting_name in beacon_channels:
        chan_name = "axis.%s.%s" % (axis.name, setting_name)
        cb = functools.partial(setting_update_from_channel, setting_name=setting_name, axis=axis) 
        if setting_value is None:
            chan = channels.Channel(chan_name, callback=cb)
        else:
            chan = channels.Channel(chan_name, setting_value, callback=cb) 
        chan._setting_update_cb = cb
        beacon_channels[setting_name] = chan

    return setting_value


class StaticConfig(object):

    NO_VALUE = Null()

    def __init__(self, config_dict):
        self.config_dict = config_dict
        try:
            config_chan_name = "config.%s" % config_dict['name']
        except KeyError:
            # can't have config channel is there is no name
            self.config_channel = None
        else:
            self.config_channel = channels.Channel(config_chan_name, dict(config_dict), callback=self._config_changed)

    def get(self, property_name, converter=str, default=NO_VALUE, 
            inherited=False):
        """Get static property

        Args:
            property_name (str): Property name
            converter (function): Default :func:`str`, Conversion function from configuration format to Python
            default: Default: NO_VALUE, default value for property
            inherited (bool): Default: False, Property can be inherited

        Returns:
            Property value

        Raises:
            KeyError, ValueError
        """
        get_method = 'get_inherited' if inherited else 'get'
        property_value = getattr(self.config_dict, get_method)(property_name)
        if property_value is not None:
            return converter(property_value)
        else:
            if default != self.NO_VALUE:
                return default

            raise KeyError("no property '%s` in config" % property_name)

    def set(self, property_name, value):
        self.config_dict[property_name] = value
   
    def save(self):
        self.config_dict.save()
        self._update_channel() 

    def reload(self):
        cfg = static.get_config()
        # this reloads *all* the configuration, hopefully it is not such
        # a big task and it can be left as simple as it is, if needed
        # we could selectively reload only parts of the config (e.g one
        # single object yml file)
        cfg.reload()
        self.config_dict = cfg.get_config(self.config_dict['name'])
        self._update_channel()

    def _update_channel(self):
        if self.config_channel is not None:
            # inform all clients that config has changed
            self.config_channel.value = dict(self.config_dict)

    def _config_changed(self, config_dict):
        for key, value in config_dict.iteritems():
            self.config_dict[key]=value

