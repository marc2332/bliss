# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import itertools
from bliss import setup_globals
from bliss.config import settings
from .session import get_current as _current_session


class _active_mg_proxy(object):
    def __getattribute__(self, attr):
        if attr == '__class__':
            return MeasurementGroup
        return getattr(get_active(), attr)

    def __setattr__(self, name, value):
        active = get_active()
        return setattr(active, name, value)
    
    def __repr__(self):
        return repr(get_active())


ACTIVE_MG = _active_mg_proxy()


def get_all():
    """
    Return all measurement groups found in the global environment
    """
    return [x for x in setup_globals.__dict__.values() if x != ACTIVE_MG and isinstance(x, MeasurementGroup)]


def get_active():
    """
    Return the current active MeasurementGroup

    Get the last known active measurement group from redis,
    or get the first found in global environment (and set it as active).
    If nothing works, returns a measurement group called None,
    which does not specify any counter.
    """
    all_mg = get_all()
    name = get_active_name()
    try:
        if name is None:
            mg = all_mg[0]
            set_active_name(mg.name)
            return mg
        else:
            for mg in all_mg:
                if name == mg.name:
                    return mg
            raise IndexError
    except IndexError:
        set_active_name(None)
        return MeasurementGroup(None, { "counters": [] })


def get_active_name():
    session = _current_session()
    session_name = session.name if session is not None else 'unnamed'
    active_mg_name = settings.SimpleSetting('%s:active_measurementgroup' % session_name)
    return active_mg_name.get()


def set_active_name(name):
    session = _current_session()
    session_name = session.name if session is not None else 'unnamed'
    active_mg_name = settings.SimpleSetting('%s:active_measurementgroup' % 
                                                 session_name)
    if name is None:
        active_mg_name.clear()
    else:
        active_mg_name.set(name)


class MeasurementGroup(object):
    def __init__(self,name,config_tree):
        """MeasurementGroup is a helper to activate detectors
        for counting procedure.

        name -- the measurement name
        config_tree -- measurement configuration.
        in this dictionary we need to have:
        counters -- a name list of available counters
        default -- if True set as default measurement
        """
        counters_list = config_tree.get('counters')
        if counters_list is None:
            raise ValueError("MeasurementGroup: should have a counters list")
        self.name = name
        self._available_counters = list(counters_list)
        self._current_config = settings.SimpleSetting('%s' % name,
                                                      default_value='default')
        # disabled counters
        self._counters_settings = settings.HashSetting('%s:%s' %
                                                       (name, self._current_config.get()))

    @property
    def state_names(self):
        """ list of states for this measurement
        """
        return list((x.split(':')[-1] for x in settings.scan(match='%s:*' % self.name)))

    @property
    def available(self):
        """available counters from the static config
        """
        return self._available_counters

    @property
    def disable(self):
        """  disabled counters name
        """
        return [name for name in self.available if name in self._counters_settings]

    @disable.setter
    def disable(self,counters):
        counter2disable = self.__counters2set(counters)
        possible2disable = set(self._available_counters).intersection(counter2disable)
        unpos2disable = counter2disable.difference(possible2disable)
        if unpos2disable:
            raise ValueError("MeasurementGroup: could not disable counters (%s)" %
                             (','.join(unpos2disable)))
        self._counters_settings.update(dict((name,True) for name in counter2disable))

    @property
    def enable(self):
        """ enabled counters name
        """
        return [name for name in self.available if name not in self._counters_settings]

    @enable.setter
    def enable(self,counters):
        counters = self.__counters2set(counters)
        possible2enable = set(self._available_counters).intersection(counters)
        unpos2enable = counters.difference(possible2enable)
        if unpos2enable:
            raise ValueError("MeasurementGroup: could not disable counters (%s)" %
                             (','.join(unpos2enable)))

        self._counters_settings.remove(*counters)

    @property
    def active_state_name(self):
        """ current configuration name for the measurment
        """
        return self._current_config.get()

    def switch_state(self,name):
        self._current_config.set(name)
        self._counters_settings = settings.HashSetting('%s:%s' %
                                                       (self.name,name))
    def remove_states(self,*state_names):
        """
        will remove one or several state(s) for this measurement
        state_name -- the state name(s) you want to remove
        """
        cnx = self._current_config._cnx()
        names = ['%s:%s' % (self.name,name) for name in state_names]
        cnx.delete(*names)
        
    def copy_from_state(self,name):
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
        s = 'MeasurementGroup:  %s (%s)\n\n' % (self.name, self.active_state_name)
        enabled = list(self.enable) + ['Enabled']
        
        max_len = max((len(x) for x in enabled))
        str_format = '  %-' + '%ds' % max_len + '  %s\n'
        s += str_format % ('Enabled','Disabled')
        s += str_format % ('-' * max_len,'-' * max_len)
        for enable,disable in itertools.izip_longest(self.enable,
                                                     self.disable,fillvalue=''):
            s += str_format % (enable,disable)
        return s

        

