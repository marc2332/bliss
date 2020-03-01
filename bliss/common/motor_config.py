# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import channels
from bliss.common.utils import Null
import time


def _get_config():
    from bliss.config import static

    return static.get_config()


class StaticConfig(object):

    NO_VALUE = Null()

    def __init__(self, config_dict):
        self.config_dict = config_dict
        self.__config_has_changed = False
        self.config_channel = None

        try:
            config_chan_name = "config.%s" % config_dict["name"]
        except KeyError:
            # can't have config channel if there is no name
            pass
        else:
            self.config_channel = channels.EventChannel(config_chan_name)
            self.config_channel.register_callback(self._config_changed)

    def get(self, property_name, converter=str, default=NO_VALUE):
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

        if self.__config_has_changed:
            self.reload()
            self.__config_has_changed = False

        property_value = self.config_dict.get(property_name)
        if property_value is not None:
            return converter(property_value)
        else:
            if default != self.NO_VALUE:
                return default

            raise KeyError("no property '%s` in config" % property_name)

    def set(self, property_name, value):
        if self.__config_has_changed:
            self.reload()
            self.__config_has_changed = False
        cfg = _get_config()
        config_node = cfg.get_config(self.config_dict["name"])
        config_node[property_name] = value
        self.config_dict = config_node.to_dict()

    def save(self):
        cfg = _get_config()
        config_node = cfg.get_config(self.config_dict["name"])
        config_node.save()
        self._update_channel()

    def reload(self):
        if self.config_channel is None:
            return
        cfg = _get_config()
        # this reloads *all* the configuration, hopefully it is not such
        # a big task and it can be left as simple as it is, if needed
        # we could selectively reload only parts of the config (e.g one
        # single object yml file)
        cfg.reload()
        config_node = cfg.get_config(self.config_dict["name"])
        self.config_dict = config_node.to_dict()

    def _update_channel(self):
        if self.config_channel is not None:
            # inform all clients that config has changed
            self.config_channel.post(time.time())

    def _config_changed(self, timestamp):
        self.__config_has_changed = True
