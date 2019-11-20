# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import itertools
import functools

from bliss import setup_globals
from bliss.config import settings
from bliss import current_session


class _active_mg_proxy(object):
    def __getattribute__(self, attr):
        if attr == "__class__":
            return MeasurementGroup
        return getattr(get_active(), attr)

    def __setattr__(self, name, value):
        return setattr(get_active(), name, value)

    def __repr__(self):
        return repr(get_active())


ACTIVE_MG = _active_mg_proxy()


def get_all():
    """
    Return a list of all measurement groups found in the global environment.
    Exclude one instance of ACTIVE_MG to avoid to return duplicated ACTIVE_MG.
    """
    return [
        x
        for x in setup_globals.__dict__.values()
        if isinstance(x, MeasurementGroup) and x != ACTIVE_MG
    ]


def get_all_names():
    """
    Return a list of all measurement groups NAMES found in the global environment.
    """
    return [
        x.name
        for x in setup_globals.__dict__.values()
        if isinstance(x, MeasurementGroup) and x != ACTIVE_MG
    ]


def get_active():
    """
    Return the current active MeasurementGroup

    Get the last known active measurement group from redis,
    or get the first found in global environment (and set it as active).
    Else return None.
    """
    all_mg = get_all()
    name = get_active_name()  # string or None
    try:
        # return the MG corresponding to <name>.
        for mg in all_mg:
            if name == mg.name:
                return mg
        # no MG named <name> or no 'active_measurementgroup'
        # found in redis: use the first MG found.
        # nothing in all_mg -> IndexError -> None
        mg = all_mg[0]
        set_active_name(mg.name)
        return mg
    except IndexError:
        return None


def get_active_name():
    """
    * search in redis the name (string) of the active MG coresponding to the session.
    * return None (NoneType) if not found.
    * !! this is only the name, the MG object may not exist.
    """
    session_name = current_session.name
    active_mg_name = settings.SimpleSetting("%s:active_measurementgroup" % session_name)
    return active_mg_name.get()


def set_active_name(name):
    # Check if <name> is an existing MG name.
    all_mg_names = get_all_names()
    if name not in all_mg_names:
        raise ValueError

    session_name = current_session.name
    active_mg_name = settings.SimpleSetting("%s:active_measurementgroup" % session_name)
    active_mg_name.set(name)


def _check_counter_name(func):
    @functools.wraps(func)
    def f(self, *counter_names, **keys):
        for cnt_name in counter_names:
            if not isinstance(cnt_name, str):
                raise TypeError(f"{func.__name__} only support string")
        return func(self, *counter_names, **keys)

    return f


class MeasurementGroup(object):
    def __init__(self, name, config_tree):
        """MeasurementGroup is a helper to activate detectors
        for counting procedure.

        name -- the measurement name
        config_tree -- measurement configuration.
        in this dictionary we need to have:
        counters -- a name list of available counters
        default -- if True set as default measurement
        """
        self.__name = name
        self.__config = config_tree

        counters_list = config_tree.get("counters")
        if counters_list is None:
            raise ValueError("MeasurementGroup: should have a counters list")
        self._available_counters = list(counters_list)

        # Current State
        self._current_state = settings.SimpleSetting(
            "%s" % name, default_value="default"
        )

        # list of states ; at least one "default" state
        self._all_states = settings.QueueSetting("%s:MG_states" % name)
        self._all_states.set(["default"])

    @property
    def name(self):
        return self.__name

    @property
    def state_names(self):
        """ Returns the list of states for this measurement group.
        """
        s_list = self._all_states.get()
        return s_list

    @property
    def available(self):
        """available counters from the static config
        """
        return self._available_counters

    @property
    def disabled(self):
        """ Disabled counter names
        """
        return set(self.disabled_setting().get())

    def disabled_setting(self):
        # key is : "<MG name>:<state_name>"  ex : "MG1:default"
        _key = "%s:%s" % (self.name, self._current_state.get())
        return settings.QueueSetting(_key)

    @_check_counter_name
    def disable(self, *counter_names):
        valid_counters = self.available
        to_disable = set(counter_names)
        disabled = set(self.disabled)

        new_disabled = disabled.union(to_disable)

        if new_disabled == set():
            self.disabled_setting().clear()
        else:
            self.disabled_setting().set(list(new_disabled))

    @property
    def enabled(self):
        """returns Enabled counter names list
        """
        return set(self.available) - set(self.disabled)

    @_check_counter_name
    def enable(self, *counter_names):
        to_enable = set(counter_names)
        disabled = set(self.disabled)
        new_disabled = disabled.difference(to_enable)

        if new_disabled == set():
            self.disabled_setting().clear()
        else:
            self.disabled_setting().set(list(new_disabled))

    @property
    def active_state_name(self):
        """ current configuration name for the measurment
        """
        return self._current_state.get()

    def disable_all(self):
        self.disable(*self.available)

    def enable_all(self):
        self.enable(*self.available)

    def set_active(self):
        set_active_name(self.name)

    def switch_state(self, state_name):
        self._current_state.set(state_name)

        # if <name> is not already a state name: create it.
        states_list = self.state_names
        if state_name not in states_list:
            # print "MG : creation of a new state: %s" % state_name
            states_list.append(state_name)
            self._all_states.set(states_list)

        # define which state is the current one.
        self._current_state.set(state_name)

    def remove_states(self, *state_names):
        """
        Remove one or several state(s) from this measurement group.
        <state_name> : the state name(s) you want to remove
        * It is not allowed to remove 'default' state : raise exception (or just purge 'default' from list ???)
        * If removing current state : swith to 'default' state  (or exception ?)

        ex:
        states_list_old = ['def', 'align', 'repare', 'bidouille']
        state_names = ['repare', 'bidouille']
        result : ['def', 'align']
        """
        if "default" in state_names:
            raise ValueError("Cannot remove 'default' state")

        if self._current_state.get() in state_names:
            self.switch_state("default")

        states_list_old = self._all_states.get()

        states_list_new = [sn for sn in states_list_old if sn not in state_names]
        self._all_states.set(states_list_new)

    def __info__(self):
        """ function used when printing a measurement group.
        """
        s = "MeasurementGroup: %s (state='%s')\n" % (self.name, self.active_state_name)
        s += "  - Existing states : "
        for name in self.state_names:
            s += "'%s'" % name + "; "
        s = s.strip("; ")
        s += "\n\n"

        enabled = list(self.enabled) + ["Enabled"]

        max_len = max((len(x) for x in enabled))
        str_format = "  %-" + "%ds" % max_len + "  %s\n"
        s += str_format % ("Enabled", "Disabled")
        s += str_format % ("-" * max_len, "-" * max_len)
        for enable, disable in itertools.zip_longest(
            self.enabled, self.disabled, fillvalue=""
        ):
            s += str_format % (enable, disable)
        return s

    def add(self, *cnt_or_names):
        """
        Add counter(s) in measurement group, and enable them
        """
        counters_names = [c if isinstance(c, str) else c.name for c in cnt_or_names]

        to_enable = set(counters_names)
        new_cnt = to_enable.difference(set(self.available))

        self._available_counters.extend(new_cnt)
        self.__config["counters"] = self._available_counters

        self.enable(*new_cnt)

        self.__config.save()

    def remove(self, *cnt_or_names):
        """
        Remove counters from measurement group
        """
        counters_names = [c if isinstance(c, str) else c.name for c in cnt_or_names]

        for cnt in counters_names:
            self.enable(cnt)
            if cnt in self._available_counters:
                self._available_counters.remove(cnt)

        self.__config["counters"] = self._available_counters

        self.__config.save()
