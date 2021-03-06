# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import collections
import itertools
import functools
import fnmatch
import typeguard
import sys
from sortedcontainers import SortedKeyList
from collections.abc import MutableSequence

from bliss.config import settings
from bliss.config.conductor.client import get_redis_proxy
from bliss import current_session
from bliss import global_map
from bliss.common.proxy import Proxy
from bliss.common.counter import Counter
from bliss.common.utils import typeguardTypeError_to_hint


def get_all():
    """
    Return a list of all measurement groups found in the global environment.
    Exclude one instance of ACTIVE_MG to avoid to return duplicated ACTIVE_MG.
    """
    try:
        return list(global_map.instance_iter("measurement groups"))
    except KeyError:
        # no measurement group has been created yet there is nothing in map
        return []


def get_all_names():
    """
    Return a list of all measurement groups NAMES found in the global environment.
    """
    return [mg.name for mg in get_all()]


def get_active():
    """
    Return the current active MeasurementGroup

    Get the last known active measurement group from redis,
    or get the first found in global environment (and set it as active).
    Else return None.
    """
    all_mg = get_all()
    name = get_active_name()  # string or None

    # return the MG corresponding to <name>.
    for mg in all_mg:
        if name == mg.name:
            return mg
    # no MG named <name> or no 'active_measurementgroup'
    # found in redis: use the first MG found.
    try:
        mg = all_mg[0]
    except IndexError:
        # nothing in all_mg -> IndexError -> None
        return None
    else:
        set_active_name(mg.name)
        return mg


def get_active_name():
    """
    * search in redis the name (string) of the active MG coresponding to the session.
    * return None (NoneType) if not found.
    * !! this is only the name, the MG object may not exist.
    """
    session_name = current_session.name
    active_mg_name = settings.SimpleSetting(
        "%s:active_measurementgroup" % session_name,
        connection=get_redis_proxy(caching=True),
    )
    return active_mg_name.get()


def set_active_name(name):
    # Check if <name> is an existing MG name.
    all_mg_names = get_all_names()
    if name not in all_mg_names:
        raise ValueError

    session_name = current_session.name
    active_mg_name = settings.SimpleSetting(
        "%s:active_measurementgroup" % session_name,
        connection=get_redis_proxy(caching=True),
    )
    active_mg_name.set(name)


def _check_counter_name(func):
    @functools.wraps(func)
    def f(self, *counter_names, **keys):
        for cnt_name in counter_names:
            if not isinstance(cnt_name, str):
                raise TypeError(f"{func.__name__} only support string")
        return func(self, *counter_names, **keys)

    return f


def counter_or_aliased_counter(cnt):
    """Return the same counter, or its alias counterpart if any
    """
    alias = global_map.aliases.get_alias(cnt)
    if alias:
        cnt = global_map.aliases.get(alias)
    return cnt


def _get_all_counters():
    return {cnt.fullname: cnt for cnt in global_map.get_counters_iter()}


def _get_counter_containers(all_counters_dict):
    counter_containers_dict = {}
    for container in _list_diff(
        global_map.instance_iter("counters"), all_counters_dict.values()
    ):
        if hasattr(container, "fullname"):
            counter_containers_dict[container.fullname] = container
        else:
            counter_containers_dict[container.name] = container
    return counter_containers_dict


def _get_default_counters(counter_containers_dict):
    default_counters = []
    try:
        for container in counter_containers_dict.values():
            try:
                default_counters.extend(container.counter_groups.default)
            except AttributeError:
                # no default group ?
                # => add all counters
                default_counters.extend(container.counters)
    except Exception:
        sys.excepthook(*sys.exc_info())
    return map(counter_or_aliased_counter, default_counters)


def _get_counters_from_names(names_list):
    """Get the counters from a names list, removing duplicated names and maintaining names order"""
    counters, missing = [], []
    counters_by_name = collections.defaultdict(set)

    all_counters_dict = _get_all_counters()
    counter_containers_dict = _get_counter_containers(all_counters_dict)
    keys = SortedKeyList(all_counters_dict)

    for cnt in all_counters_dict.values():
        counters_by_name[cnt.name].add(cnt)
        counters_by_name[cnt.fullname].add(cnt)
        alias_obj = global_map.aliases.get(cnt.name)
        if alias_obj:
            counters_by_name[alias_obj.original_name].add(cnt)
            counters_by_name[alias_obj.original_fullname].add(cnt)

    for name in _remove_duplicated(names_list):
        # try to get counter by name
        cnts = counters_by_name.get(name)
        if cnts is not None:
            # check if there is a unique counter with this name
            if len(cnts) > 1:
                raise RuntimeError(
                    f"Several counters may be selected with this {name}\n"
                    f" change for one of those: {', '.join(cnt.fullname for cnt in cnts)}"
                )
            # add counter and continue
            counters += cnts
            continue

        if name in counter_containers_dict:
            # look for all counters below this container
            name += ":"

        # get counters by their full name
        index = keys.bisect_key_left(name)
        try:
            index_name = keys[index]
        except IndexError:
            index -= 1
            try:
                index_name = keys[index]
            except IndexError:
                missing.append(name)
                continue

        if index_name == name:
            counters += _get_counters_from_object(all_counters_dict[name])
        else:  # match partial names
            counter_container_name = name.rstrip(":") + ":"
            # counter container case
            if index_name.startswith(counter_container_name):
                counters.append(all_counters_dict[index_name])
                for i in range(index + 1, len(keys)):
                    index_name = keys[i]
                    if not index_name.startswith(counter_container_name):
                        break
                    counters.append(all_counters_dict[index_name])
            else:
                missing.append(name)
    return counters, missing


def _get_counters_from_measurement_group(mg):
    available_counters = mg._available_counters
    enabled_counter_names = mg._get_enabled_counters_names(available_counters)
    counters = [c for c in available_counters if c.fullname in enabled_counter_names]

    missing = _list_diff(enabled_counter_names, mg._get_counters_names(counters))
    if missing:
        raise RuntimeError(
            f"Missing counters in measurement group {mg.name}: {', '.join(missing)}"
        )
    else:
        return list(counters)


def _get_counters_from_object(arg):
    """Get the counters from a bliss object (typically a scan function
    positional counter argument).

    Arguments:
        arg: Can be:

             - a counter
             - a counter namespace
             - a controller, in which case:

                - controller.groups.default namespace is used if it exists
                - controller.counters namespace otherwise

             - a measurementgroup
    """
    counters = []
    try:
        counters = list(arg.counter_groups.default)
    except AttributeError:
        try:
            counters = list(arg.counters)
        except AttributeError:
            pass
    if not counters:
        try:
            counters = list(arg)
        except TypeError:
            counters = [arg]
    # replace counters with their aliased counterpart, if any
    for i, cnt in enumerate(counters):
        counters[i] = counter_or_aliased_counter(cnt)
    return counters


def _remove_duplicated(input_list):
    """ remove duplicated elements of a list and maintain order (like an ordered set) """
    return list(dict.fromkeys(input_list))


def _list_diff(l1, l2):
    """ returns elements of l1 which are not in l2 """
    return [x for x in l1 if (x not in l2)]


class MeasurementGroup:
    def __init__(self, name, config_tree):
        """MeasurementGroup is a helper to activate detectors
        for counting procedure.

        name -- the measurement name
        config_tree -- measurement configuration.
        in this dictionary we need to have:
        counters -- a name list of available counters
        default -- if True set as default measurement
        """
        global_map.register(self, parents_list=["measurement groups"])

        self.__name = name
        self.__config = config_tree

        if not isinstance(config_tree.get("counters"), MutableSequence):
            raise ValueError("MeasurementGroup: should have a counters list")

        # ordered list of counter fullnames
        self._config_counters = config_tree.get("counters")
        self._extra_counters = []

        # Current State
        self._current_state = settings.SimpleSetting(
            "%s" % name,
            default_value="default",
            connection=get_redis_proxy(caching=True),
        )

        # list of states ; at least one "default" state
        self._all_states = settings.QueueSetting(
            "%s:MG_states" % name, connection=get_redis_proxy(caching=True)
        )
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

    def _get_counters_names(self, counters):
        return [cnt.fullname for cnt in counters]

    @property
    def available(self):
        """available counters from the static config
        """
        return self._get_counters_names(self._available_counters)

    @property
    def _available_counters(self):
        counters, _ = _get_counters_from_names(
            itertools.chain(self._config_counters, self._extra_counters)
        )
        return counters

    def _get_disabled_counters_names(self, available_counters):
        """Return list of disabled counters

        Remove counters from redis that are not in config, if any
        """
        available_counters = self._get_counters_names(available_counters)

        s = set(self._disabled_setting.get())
        disabled_counters = [name for name in available_counters if name in s]

        not_present_counters = []
        for cnt_fullname in disabled_counters:
            if (
                cnt_fullname not in available_counters
                and cnt_fullname not in self._extra_counters
            ):
                not_present_counters.append(cnt_fullname)

        return _list_diff(disabled_counters, not_present_counters)

    @property
    def disabled(self):
        """ Disabled counter names
        """
        return self._get_disabled_counters_names(self._available_counters)

    @property
    def _disabled_setting(self):
        # key is : "<MG name>:<state_name>"  ex : "MG1:default"
        _key = "%s:%s" % (self.name, self._current_state.get())
        return settings.QueueSetting(_key, connection=get_redis_proxy(caching=True))

    @_check_counter_name
    def disable(self, *counter_patterns):
        available_counters = self._available_counters
        counter_names = self._find_counter_names(counter_patterns, available_counters)

        if not counter_names:
            raise ValueError(
                f"No match, could not disable any counter with patterns: {','.join(counter_patterns)}"
            )

        disabled = self._get_disabled_counters_names(available_counters)
        disabled.extend(counter_names)

        if not disabled:
            self._disabled_setting.clear()
        else:
            self._disabled_setting.set(disabled)

    def _get_enabled_counters_names(self, available_counters):
        return _list_diff(
            self._get_counters_names(available_counters),
            self._get_disabled_counters_names(available_counters),
        )

    @property
    def enabled(self):
        """returns Enabled counter names list
        """
        return self._get_enabled_counters_names(self._available_counters)

    def _find_counter_names(self, counter_patterns, available_counters):
        default_group_counters = self._get_counters_names(
            _get_default_counters(_get_counter_containers(_get_all_counters()))
        )

        counter_names = []
        for counter_pattern in counter_patterns:
            if counter_pattern in (
                name.split(":")[0] for name in default_group_counters
            ):
                # not a 'glob'-like pattern
                counter_names.extend(
                    cnt_name
                    for cnt_name in default_group_counters
                    if cnt_name == counter_pattern
                    or cnt_name.startswith(counter_pattern + ":")
                )
            else:
                counter_names.extend(
                    cnt.fullname
                    for cnt in available_counters
                    if fnmatch.fnmatch(cnt.fullname, counter_pattern)
                    or fnmatch.fnmatch(cnt.name, counter_pattern)
                )
        return counter_names

    @_check_counter_name
    def enable(self, *counter_patterns):
        available_counters = self._available_counters
        counter_names = self._find_counter_names(counter_patterns, available_counters)

        if not counter_names:
            raise ValueError(
                f"No match, could not enable any counter with patterns: {','.join(counter_patterns)}"
            )

        new_disabled = _list_diff(
            self._get_disabled_counters_names(available_counters), counter_names
        )

        if not new_disabled:
            self._disabled_setting.clear()
        else:
            self._disabled_setting.set(new_disabled)

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
        available_counters = self._available_counters
        enabled_counters = self._get_enabled_counters_names(available_counters)
        disabled_counters = self._get_disabled_counters_names(available_counters)

        info_str = "MeasurementGroup: %s (state='%s')\n" % (
            self.name,
            self.active_state_name,
        )
        info_str += "  - Existing states : "
        for name in self.state_names:
            info_str += "'%s'" % name + "; "
        info_str = info_str.strip("; ")
        info_str += "\n\n"

        enabled = list(enabled_counters) + ["Enabled"]

        max_len = max((len(x) for x in enabled))
        str_format = "  %-" + "%ds" % max_len + "  %s\n"
        info_str += str_format % ("Enabled", "Disabled")
        info_str += str_format % ("-" * max_len, "-" * max_len)
        for enable, disable in itertools.zip_longest(
            enabled_counters, disabled_counters, fillvalue=""
        ):
            info_str += str_format % (enable, disable)

        return info_str

    @typeguardTypeError_to_hint
    @typeguard.typechecked
    def add(self, *counters: Counter):
        """
        Add counter(s) in measurement group, and enable them
        """
        to_enable = self._get_counters_names(counters)
        new_cnt = _list_diff(to_enable, self.available)
        self._extra_counters.extend(new_cnt)
        self.enable(*new_cnt)

    @typeguardTypeError_to_hint
    @typeguard.typechecked
    def remove(self, *counters: Counter):
        """
        Remove counters from measurement group
        """
        counter_names = self._get_counters_names(counters)
        all_config_counters, _ = _get_counters_from_names(self._config_counters)
        all_config_counters_names = self._get_counters_names(all_config_counters)

        for cnt_name in counter_names:
            if cnt_name in all_config_counters_names:
                raise ValueError(
                    f"{self.name}: cannot remove counter defined in configuration"
                )
            try:
                self._extra_counters.remove(cnt_name)
            except ValueError:
                pass


class ActiveMeasurementGroupProxy(Proxy):
    def __init__(self):
        object.__setattr__(self, "__mg_class__", MeasurementGroup)

        super().__init__(get_active)

    @property
    def __class__(self):
        return self.__mg_class__


ACTIVE_MG = ActiveMeasurementGroupProxy()
