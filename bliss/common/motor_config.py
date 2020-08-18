# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import channels
from bliss.common.utils import Null
import time


class StaticConfig(object):

    NO_VALUE = Null()

    def __init__(self, config_node):
        if isinstance(config_node, dict):
            # soft axes controller => no reload, no save
            self.__config_node = None
            self.__config_dict = config_node
        else:
            self.__config_node = config_node
            self.__config_dict = config_node.to_dict()

        self.__config_has_changed = False
        self.config_channel = None

        try:
            config_chan_name = "config.%s" % self.config_dict["name"]
        except KeyError:
            # can't have config channel if there is no name
            pass
        else:
            self.config_channel = channels.EventChannel(config_chan_name)
            self.config_channel.register_callback(self._config_changed)

    @property
    def config_node(self):
        return self.__config_node

    @property
    def config_dict(self):
        return self.__config_dict

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

        if self.config_node:
            property_value = self.config_node.get(property_name)  # solve references
        else:
            property_value = self.config_dict.get(property_name)
        if property_value is not None:
            if callable(converter):
                return converter(property_value)
            else:
                return property_value
        else:
            if default != self.NO_VALUE:
                return default

            raise KeyError("no property '%s` in config" % property_name)

    def set(self, property_name, value):
        if self.__config_has_changed:
            self.reload()
            self.__config_has_changed = False
        if self.config_node is None:
            self.config_dict[property_name] = value
        else:
            self.config_node[property_name] = value

    def save(self):
        if self.config_node is not None:
            self.config_node.save()
        self._update_channel()

    def reload(self):
        if self.config_channel is None:
            return
        if self.config_node is None:
            return
        self.config_node.reload()
        self.config_dict.clear()
        self.config_dict.update(self.config_node.to_dict())

    def _update_channel(self):
        if self.config_channel is not None:
            # inform all clients that config has changed
            self.config_channel.post(time.time())

    def _config_changed(self, timestamp):
        self.__config_has_changed = True
