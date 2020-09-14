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
from sortedcontainers import SortedKeyList
from collections.abc import MutableSequence

from bliss.config import settings
from bliss.config.settings_cache import get_redis_client_cache
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
        "%s:active_measurementgroup" % session_name, connection=get_redis_client_cache()
    )
    return active_mg_name.get()


class ActiveMeasurementGroupProxy(Proxy):
    def __init__(self):
        super().__init__(get_active)


ACTIVE_MG = ActiveMeasurementGroupProxy()


def set_active_name(name):
    # Check if <name> is an existing MG name.
    all_mg_names = get_all_names()
    if name not in all_mg_names:
        raise ValueError

    session_name = current_session.name
    active_mg_name = settings.SimpleSetting(
        "%s:active_measurementgroup" % session_name, connection=get_redis_client_cache()
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


def _get_counters_from_names(names_list, container_default_counters_only=False):
    """Get the counters from a names list"""
    counters, missing = [], []
    counters_by_name = collections.defaultdict(set)
    all_counters_dict = dict()

    all_counters = set(global_map.get_counters_iter())
    for cnt in all_counters:
        all_counters_dict[cnt.fullname] = cnt
        counters_by_name[cnt.name].add(cnt)
        counters_by_name[cnt.fullname].add(cnt)
        alias_obj = global_map.aliases.get(cnt.name)
        if alias_obj:
            counters_by_name[alias_obj.original_name].add(cnt)
            counters_by_name[alias_obj.original_fullname].add(cnt)
    counter_containers_dict = {}
    for container in set(global_map.instance_iter("counters")) - all_counters:
        if hasattr(container, "fullname"):
            counter_containers_dict[container.fullname] = container
        else:
            counter_containers_dict[container.name] = container
    keys = SortedKeyList(all_counters_dict)
    for name in set(names_list):
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
            if container_default_counters_only:
                try:
                    default_counters = counter_containers_dict[
                        name
                    ].counter_groups.default
                except AttributeError:
                    # no default group ?
                    # fallback to all counters below this container
                    pass
                except Exception:
                    pass
                else:
                    # add default counters
                    counters += map(counter_or_aliased_counter, default_counters)
                    continue
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
    try:
        counters, missing = _get_counters_from_names(mg.enabled)
    except RuntimeError as e:
        raise RuntimeError(f"{mg.name}: {e}")
    if missing:
        raise AttributeError(*missing)
    else:
        return counters


def _get_counters_from_object(arg):
    """Get the counters from a bliss object (typically a scan function
    positional counter argument).

    According to issue #251, `arg` can be:
    - a counter
    - a counter namepace
    - a controller, in which case:
       - controller.groups.default namespace is used if it exists
       - controller.counters namepace otherwise
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
        self._config_counters = config_tree.get("counters")
        self._extra_counters = []

        # Current State
        self._current_state = settings.SimpleSetting(
            "%s" % name, default_value="default", connection=get_redis_client_cache()
        )

        # list of states ; at least one "default" state
        self._all_states = settings.QueueSetting(
            "%s:MG_states" % name, connection=get_redis_client_cache()
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

    @property
    def available(self):
        """available counters from the static config
        """
        return set(cnt.fullname for cnt in self._available_counters)

    @property
    def _available_counters(self):
        counters, _ = _get_counters_from_names(
            itertools.chain(self._config_counters, self._extra_counters)
        )
        return set(counters)

    @property
    def disabled(self):
        """ Disabled counter names
        """
        # remove counters from redis that are not in config, if any
        available_counters = self.available
        disabled_counters = set(self._disabled_setting.get())
        not_present_counters = set()
        for cnt_fullname in disabled_counters:
            if (
                cnt_fullname not in available_counters
                and cnt_fullname not in self._extra_counters
            ):
                not_present_counters.add(cnt_fullname)
        return disabled_counters - not_present_counters

    @property
    def _disabled_setting(self):
        # key is : "<MG name>:<state_name>"  ex : "MG1:default"
        _key = "%s:%s" % (self.name, self._current_state.get())
        return settings.QueueSetting(_key, connection=get_redis_client_cache())

    @_check_counter_name
    def disable(self, *counter_patterns):
        counters, _ = _get_counters_from_names(
            self._config_counters, container_default_counters_only=True
        )
        counter_names = self._find_counter_names(counters, counter_patterns)

        to_disable = set(counter_names)
        if not to_disable:
            raise ValueError(
                f"No match, could not disable any counter with patterns: {','.join(counter_patterns)}"
            )
        disabled = set(self.disabled)

        new_disabled = disabled.union(to_disable)

        if new_disabled == set():
            self._disabled_setting.clear()
        else:
            self._disabled_setting.set(list(new_disabled))

    @property
    def enabled(self):
        """returns Enabled counter names list
        """
        return set(self.available) - set(self.disabled)

    def _find_counter_names(self, counters, counter_patterns):
        default_group_counters = set(cnt.fullname for cnt in counters)
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
                    for cnt in self._available_counters
                    if fnmatch.fnmatch(cnt.fullname, counter_pattern)
                    or fnmatch.fnmatch(cnt.name, counter_pattern)
                )
        return counter_names

    @_check_counter_name
    def enable(self, *counter_patterns):
        counters, _ = _get_counters_from_names(
            self._config_counters, container_default_counters_only=True
        )
        counter_names = self._find_counter_names(counters, counter_patterns)

        to_enable = set(counter_names)
        if not to_enable:
            raise ValueError(
                f"No match, could not enable any counter with patterns: {','.join(counter_patterns)}"
            )

        disabled = set(self.disabled)
        new_disabled = disabled.difference(to_enable)

        if new_disabled == set():
            self._disabled_setting.clear()
        else:
            self._disabled_setting.set(list(new_disabled))

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
        info_str = "MeasurementGroup: %s (state='%s')\n" % (
            self.name,
            self.active_state_name,
        )
        info_str += "  - Existing states : "
        for name in self.state_names:
            info_str += "'%s'" % name + "; "
        info_str = info_str.strip("; ")
        info_str += "\n\n"

        enabled = list(self.enabled) + ["Enabled"]

        max_len = max((len(x) for x in enabled))
        str_format = "  %-" + "%ds" % max_len + "  %s\n"
        info_str += str_format % ("Enabled", "Disabled")
        info_str += str_format % ("-" * max_len, "-" * max_len)
        for enable, disable in itertools.zip_longest(
            sorted(self.enabled), sorted(self.disabled), fillvalue=""
        ):
            info_str += str_format % (enable, disable)

        return info_str

    @typeguardTypeError_to_hint
    @typeguard.typechecked
    def add(self, *counters: Counter):
        """
        Add counter(s) in measurement group, and enable them
        """
        counter_names = [cnt.fullname for cnt in counters]

        to_enable = set(counter_names)
        new_cnt = to_enable.difference(set(self.available))

        self._extra_counters.extend(new_cnt)

        self.enable(*new_cnt)

    @typeguardTypeError_to_hint
    @typeguard.typechecked
    def remove(self, *counters: Counter):
        """
        Remove counters from measurement group
        """
        counter_names = [cnt.fullname for cnt in counters]
        all_config_counters, _ = _get_counters_from_names(self._config_counters)
        all_config_counters = (cnt.fullname for cnt in all_config_counters)

        for cnt in counter_names:
            if cnt in all_config_counters:
                raise ValueError(
                    f"{self.name}: cannot remove counter defined in configuration"
                )
            self.enable(cnt)
            try:
                self._extra_counters.remove(cnt)
            except ValueError:
                pass
