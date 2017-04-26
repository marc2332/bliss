# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import channels
from bliss.common.utils import Null
from bliss.config.static import get_config

class StaticConfig(object):

    NO_VALUE = Null()

    def __init__(self, config_dict):
        self.config_dict = config_dict
        self.config_channel = None

        try:
            config_chan_name = "config.%s" % config_dict['name']
        except KeyError:
            # can't have config channel is there is no name
            pass
        else:
            if not 'axes' in config_dict and not 'encoders' in config_dict:
                # axis config
                self.config_channel = channels.Channel(config_chan_name, config_dict.to_dict(), callback=self._config_changed)

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
        cfg = get_config()
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


