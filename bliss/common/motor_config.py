# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import channels
from bliss.common.utils import Null
import time


class MotorConfig:
    def __init__(self, config_node):
        self.__config_dict = config_node
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
    def config_dict(self):
        return self.__config_dict

    def get(self, property_name, converter=str, default=None):
        """Get static property

        Args:
            property_name (str): Property name
            converter (function): Default :func:`str`, Conversion function from configuration format to Python
            default: default value for property if key does not exist (defaults to None)

        Returns:
            Property value

        Raises:
            KeyError, ValueError
        """

        if self.__config_has_changed:
            self.reload()
            self.__config_has_changed = False
        property_value = self.config_dict.get(property_name)
        if property_value is None:
            return default
        else:
            if callable(converter):
                return converter(property_value)
            else:
                return property_value

    def set(self, property_name, value):
        if self.__config_has_changed:
            self.reload()
            self.__config_has_changed = False
        self.config_dict[property_name] = value

    def save(self):
        if isinstance(self.config_dict, dict):
            return
        self.config_dict.save()
        self._update_channel()

    def reload(self):
        if self.config_channel is None:
            return
        if isinstance(self.config_dict, dict):
            return
        self.config_dict.reload()

    def _update_channel(self):
        if self.config_channel is not None:
            # inform all clients that config has changed
            self.config_channel.post(time.time())

    def _config_changed(self, timestamp):
        self.__config_has_changed = True
