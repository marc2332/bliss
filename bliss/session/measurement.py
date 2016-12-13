# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import itertools
from bliss.config import settings

DEFAULT_MEASUREMENT = None

def get_default() :
    return DEFAULT_MEASUREMENT

class Measurement(object):
    def __init__(self,name,config_tree):
        """Measurement is a helper to activate detectors
        for counting procedure.

        name -- the measurement name
        config_tree -- measurement configuration.
        in this dictionary we need to have:
        counters -- a name list of available counters
        default -- if True set as default measurement
        """
        counters_list = config_tree.get('counters')
        if counters_list is None:
            raise ValueError("Measurement: should have a counters list")
        self.name = name
        self._available_counters = set(counters_list)
        self._current_config = settings.SimpleSetting('%s' % name,
                                                      default_value='default')
        self._counters_settings = settings.HashSetting('%s:%s' %
                                                       (name, self._current_config.get()))
        global DEFAULT_MEASUREMENT
        if(DEFAULT_MEASUREMENT is None or
           config_tree.get('default',False)):
            DEFAULT_MEASUREMENT = self

    @property
    def config_names(self):
        """ list of configuration for this measurement
        """
        return list((x.split(':')[-1] for x in settings.scan(match='%s:*' % self.name)))

    def remove_config(self,*config_names):
        cnx = self._current_config._cnx()
        names = ['%s:%s' % (self.name,name) for name in config_names]
        cnx.delete(*names)
        
    @property
    def available(self):
        """available counters from the static config
        """
        return self._available_counters

    @property
    def enable(self):
        """  enabled counters name
        """
        return self._counters_settings.keys()
    @enable.setter
    def enable(self,counters):
        counter2enable = self.__counters2set(counters)
        possible2enable = self._available_counters.intersection(counter2enable)
        unpos2enable = counter2enable.difference(possible2enable)
        if unpos2enable:
            raise ValueError("Measurement: couldn't not enable counters (%s)" %
                             (','.join(unpos2enable)))
        self._counters_settings.update(dict((name,True) for name in counter2enable))
    @property
    def disable(self):
        """ disabled counters name
        """
        enable_counters = set(self._counters_settings.keys())
        return self._available_counters.difference(enable_counters)
    @disable.setter
    def disable(self,counters):
        counters = self.__counters2set(counters)
        self._counters_settings.remove(*counters)
    @property
    def config_name(self):
        """ current configuration name for the measurment
        """
        return self._current_config.get()

    def switch(self,name):
        self._current_config.set(name)
        self._counters_settings = settings.HashSetting('%s:%s' %
                                                       (self.name,name))
    def remove(self,name):
        """
        will remove a configuration for this measurement
        name -- the configuration name you want to remove
        """
        tmp_hash = settings.HashSetting('%s:%s' % (self.name,name))
        tmp_hash.clear()

    def copy_from(self,name):
        """
        this will copy the configuration into the current
        """
        tmp_hash = settings.HashSetting('%s:%s' % (self.name,name))
        self._counters_settings.clear()
        for k,v in tmp_hash.iteritems():
            self._counters_settings[k] = v
            
    def __counters2set(self,counters):
        if not isinstance(counters,(tuple,list,set)):
            counters = list((counters,))
        return set((x.name if hasattr(x,'name') else x for x in counters))

    def __repr__(self):
        s = 'Measurement:  (%s)\n\n' % self._current_config.get()
        enabled = list(self.enable) + ['Enabled']
        max_len = max((len(x) for x in enabled))
        str_format = '  %-' + '%ds' % max_len + '  %s\n'
        s += str_format % ('Enabled','Disabled')
        s += str_format % ('-' * max_len,'-' * max_len)
        for enable,disable in itertools.izip_longest(self.enable,
                                                     self.disable,fillvalue=''):
            s += str_format % (enable,disable)
        return s
        
