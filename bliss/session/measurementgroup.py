# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import itertools
from bliss import setup_globals
from bliss.config import settings
from bliss.session.session import get_default as _default_session

DEFAULT_MEASUREMENT = None

def get_all() :
    """
    Return all available measurement group found in the global environment
    """
    return [x for x in setup_globals.__dict__.values() if isinstance(x,MeasurementGroup)]

def get_active() :
    """
    Return the MeasurementGroup which is active.

    If no measurement group is set, try to find the last used
    if still available or the first found in the global environment.
    """
    global DEFAULT_MEASUREMENT
    if DEFAULT_MEASUREMENT is None:
        measurement_grp = setup_globals.__dict__.get(_active_name())
        if measurement_grp is None:
            all_mes = get_all()
            if all_mes:
                set_active(all_mes[0])
        else:
            DEFAULT_MEASUREMENT = measurement_grp
    return DEFAULT_MEASUREMENT

def set_active(measurementgroup):
    """
    Change the active measurement group.
    """
    global DEFAULT_MEASUREMENT
    if measurementgroup is None:
        _active_name(None)
        DEFAULT_MEASUREMENT = None
    else:
        _active_name(measurementgroup.name)
        DEFAULT_MEASUREMENT = measurementgroup

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
        self._available_counters = set(counters_list)
        self._current_config = settings.SimpleSetting('%s' % name,
                                                      default_value='default')
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
        return self._available_counters.intersection(self._counters_settings.keys())
    @disable.setter
    def disable(self,counters):
        counter2disable = self.__counters2set(counters)
        possible2disable = self._available_counters.intersection(counter2disable)
        unpos2disable = counter2disable.difference(possible2disable)
        if unpos2disable:
            raise ValueError("MeasurementGroup: couldn't not disable counters (%s)" %
                             (','.join(unpos2disable)))
        self._counters_settings.update(dict((name,True) for name in counter2disable))
    @property
    def enable(self):
        """ enabled counters name
        """
        disabled_counters = set(self._counters_settings.keys())
        return self._available_counters.difference(disabled_counters)
    @enable.setter
    def enable(self,counters):
        counters = self.__counters2set(counters)
        possible2enable = self._available_counters.intersection(counters)
        unpos2enable = counters.difference(possible2enable)
        if unpos2enable:
            raise ValueError("MeasurementGroup: couldn't not disable counters (%s)" %
                             (','.join(unpos2enable)))

        self._counters_settings.remove(*counters)
    @property
    def state_names(self):
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
        s = 'MeasurementGroup:  %s (%s)\n\n' % (self.name,self._current_config.get())
        enabled = list(self.enable) + ['Enabled']
        max_len = max((len(x) for x in enabled))
        str_format = '  %-' + '%ds' % max_len + '  %s\n'
        s += str_format % ('Enabled','Disabled')
        s += str_format % ('-' * max_len,'-' * max_len)
        for enable,disable in itertools.izip_longest(sorted(self.enable),
                                                     sorted(self.disable),fillvalue=''):
            s += str_format % (enable,disable)
        return s
        



def _active_name(name = ""):
    session = _default_session()
    session_name = session.name if session is not None else 'unnamed'
    active_measure_name = settings.SimpleSetting('%s:active_measurementgroup' % 
                                                 session_name)
    if name or name is None:
        active_measure_name.set(name)
    else:
        return active_measure_name.get()

class default_mg(object):
  def __getattribute__(self, attr):
    return getattr(get_active(), attr)
  def __setattr__(self,name,value):
    active = get_active()
    return setattr(active,name,value)
  def __repr__(self):
    return repr(get_active())
