# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Classes related to the alias handling in Bliss

The alias serves the following purposes:
- Handle potential duplication of motor names in a beamline-wide configuration 
- Shorten key names e.g. in the hdf5 files while conserving uniqueness of the keys 
"""
import itertools
import functools
import weakref
import gevent
from tabulate import tabulate
from bliss.common.proxy import Proxy
from bliss.common.mapping import Map
from bliss.common.utils import safe_get


class CounterWrapper:
    def __init__(self, fullname, counter_controller):
        self.__fullname = fullname
        self.__counter_controller = counter_controller

    def __call__(self):
        """Return a counter object from a fullname like:
        * 'lima_simulator:r1_sum'
        * 'lima_simulator:bpm:x'
        * 'simu1:deadtime_det0'
        """
        counters = self.__counter_controller.counters
        for cnt in counters:
            if cnt.fullname == self.__fullname:
                return cnt
        raise RuntimeError(
            f"Alias: cannot find counter corresponding to {self.__fullname}"
        )


class CounterAlias(Proxy):
    def __init__(self, alias_name, cnt):
        if isinstance(cnt, Proxy):
            raise RuntimeError(
                f"Object {cnt.fullname} already has an alias: {cnt.name}"
            )
        # we do not want to go through the heavy process of
        # obtaining the counter object behind the proxy if
        # we just want to access its name or its class
        object.__setattr__(self, "__cnt_fullname__", cnt.fullname)
        object.__setattr__(self, "__cnt_name__", cnt.name)
        object.__setattr__(self, "__cnt_hash__", hash(cnt))
        try:
            object.__setattr__(
                self, "__cnt_conversion_function__", cnt.conversion_function
            )
        except AttributeError:
            object.__setattr__(self, "__cnt_conversion_function__", None)
        object.__setattr__(self, "__alias_name__", alias_name)
        object.__setattr__(self, "__cnt_class__", cnt.__class__)

        # the CounterAlias holds a reference to the counter controller
        super().__init__(CounterWrapper(cnt.fullname, cnt._counter_controller))

    @property
    def __class__(self):
        return self.__cnt_class__

    @property
    def object_ref(self):
        return self.__wrapped__

    @property
    def name(self):
        return self.__alias_name__

    @property
    def fullname(self):
        return self.__cnt_fullname__

    @property
    def original_name(self):
        return self.__cnt_name__

    @property
    def conversion_function(self):
        return self.__cnt_conversion_function__

    # this is to speed up comparisons (there are a lot !),
    # to not go through the .counters everytime
    def __eq__(self, other):
        try:
            return self.fullname == other.fullname
        except AttributeError:
            return False

    def __hash__(self):
        return self.__cnt_hash__

    def create_acquisition_device(self, *args, **kwargs):
        return self.__wrapped__.create_acquisition_device.__func__(
            self, *args, **kwargs
        )


class ObjectAlias(Proxy):
    def __init__(self, alias_name, obj):
        if isinstance(obj, Proxy):
            raise RuntimeError(
                f"Object {obj.original_name} already has an alias: {obj.name}"
            )
        object.__setattr__(self, "__alias_name__", alias_name)
        object.__setattr__(self, "__obj_name__", obj.name)
        super().__init__(lambda: obj, init_once=True)

    @property
    def name(self):
        return self.__alias_name__

    @property
    def original_name(self):
        return self.__obj_name__

    @property
    def object_ref(self):
        return self.__wrapped__


class Aliases:
    """Helper class to manage aliases list: display, add
    """

    def __init__(self, objects_map, current_session):
        self.__map = objects_map
        self.__aliases_dict = weakref.WeakValueDictionary()
        self.__session = current_session

    def __create_alias(self, alias_name, obj_or_name, verbose=False):
        """Create an alias from an original object name or instance
        Parameters:
            - alias_name: (new) name that will be assigned to the alias
            - obj_or_name: (old) name or object that will be masked by the alias_name
        Keyword Arguments:
            - verbose: flag to print user information message
        """
        original_object = None
        alias_obj = None

        if isinstance(obj_or_name, str):
            fullname = obj_or_name  # can be a motor name or a counter fullname

            # check if object exists
            for obj in self.__map.get_axes_iter():
                if obj.name == fullname:
                    original_object = obj
                    alias_obj = ObjectAlias(alias_name, obj)
                    break
            else:
                # counter
                try:
                    obj = self.__map.get_counter_from_fullname(fullname)
                except AttributeError:
                    pass
                else:
                    original_object = obj
                    alias_obj = CounterAlias(alias_name, obj)
            if alias_obj is None:
                raise RuntimeError(
                    f"Cannot make alias '{alias_name}' for '{fullname}': object does not exist, or has an invalid type"
                )
        else:
            obj = obj_or_name
            original_object = obj

            if obj in self.__map.get_axes_iter():
                alias_obj = ObjectAlias(alias_name, obj)
            else:
                # cannot use directly 'obj in self.__map.get_counters_iter()'
                # because counters are generated on-the-fly for the moment,
                # thus objects change each time
                try:
                    fn = obj.fullname
                except AttributeError:
                    raise TypeError(
                        f"Cannot make an alias of object of type {type(obj)}"
                    )
                else:
                    for cnt in self.__map.get_counters_iter():
                        if cnt.fullname == fn:
                            alias_obj = CounterAlias(alias_name, obj)
                            break
                    else:
                        raise TypeError(
                            f"Could not find a counter with corresponding name: {fn}"
                        )

        # create alias object
        self.__aliases_dict[alias_name] = alias_obj

        # assign object to alias name in env dict
        self.__session.env_dict[alias_name] = alias_obj
        # delete old object from env dict
        try:
            if self.__session.env_dict.get(original_object.name) is original_object:
                del self.__session.env_dict[original_object.name]
        except KeyError:
            pass

        return alias_obj

    def add(self, alias_name, obj_or_name, verbose=True):
        if alias_name in self.__session.config.names_list:
            raise RuntimeError(
                "Invalid alias name: it corresponds to a configuration object"
            )
        if alias_name in self.__session.env_dict:
            raise RuntimeError("Invalid alias name: would overwrite an existing object")
        if alias_name in self.__aliases_dict:
            raise RuntimeError("Alias already exists")
        if self.get_alias(obj_or_name):
            raise RuntimeError("Object already has an alias")

        return self.__create_alias(alias_name, obj_or_name, verbose)

    def remove(self, alias_name):
        alias = self.__aliases_dict.pop(alias_name, None)
        if alias:
            del self.__session.env_dict[alias_name]

    def get(self, alias_name):
        return self.__aliases_dict.get(alias_name)

    def set(self, alias_name, obj_or_name, verbose=True):
        alias = self.get(alias_name)
        if alias:
            try:
                self.remove(alias_name)
                return self.add(alias_name, obj_or_name, verbose)
            except Exception:
                self.__aliases_dict[alias_name] = alias
                self.__session.env_dict[alias_name] = alias
                raise

    def get_alias(self, obj_or_name):
        if isinstance(obj_or_name, str):
            # name
            for alias in self:
                if alias.original_name == obj_or_name:
                    return alias.name
                else:
                    try:
                        if alias.fullname == obj_or_name:
                            return alias.name
                    except AttributeError:
                        continue
            return None
        else:
            # obj
            obj = obj_or_name
            for alias in self:
                if alias == obj:
                    return alias.name

    def __iter__(self):
        for alias in self.__aliases_dict.values():
            yield alias

    def names_iter(self):
        return self.__aliases_dict.keys()

    def list_aliases(self):
        """Display the list of all aliases"""
        table_info = []
        for alias in self:
            try:
                alias_original_fullname = alias.fullname
            except AttributeError:
                alias_original_fullname = alias.original_name
            table_info.append([alias.name, alias_original_fullname])
        return str(tabulate(table_info, headers=["Alias", "Original fullname"]))

    def __info__(self):
        return self.list_aliases()


class MapWithAliases(Map):
    def __init__(self, current_session, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__current_session = current_session
        self.__aliases = Aliases(self, current_session)

    def clear(self):
        super().clear()
        self.__aliases = Aliases(self, self.__current_session)

    def get_axes_iter(self):
        for mot in self.instance_iter("axes"):
            yield mot

    def get_counters_iter(self):
        for counter_or_container in self.instance_iter("counters"):
            try:
                # let's see first if we have a counter container
                # TODO: replace with proper 'CounterContainer' abc/protocol/whatever
                # (anything, but needs to be **defined**)
                for cnt in counter_or_container.counters:
                    yield cnt
            except AttributeError:
                # must be a counter object
                yield counter_or_container
            except Exception:
                continue

        for obj in self.aliases:
            if isinstance(obj, CounterAlias):
                yield obj

    @property
    def aliases(self):
        return self.__aliases

    def alias_or_name(self, obj):
        return self.aliases.get_alias(obj) or obj.name

    def get_axes_names_iter(self):
        for axis in self.get_axes_iter():
            yield self.alias_or_name(axis)

    def get_axes_positions_iter(self, on_error=None):
        def request(axis):
            return (
                self.alias_or_name(axis),
                safe_get(axis, "position", on_error),
                safe_get(axis, "dial", on_error),
                axis.config.get("unit", default=None),
            )

        tasks = list()
        for axis in self.get_axes_iter():
            tasks.append(gevent.spawn(request, axis))

        gevent.joinall(tasks)

        yield from (task.get() for task in tasks)

    def get_axis_objects_iter(self, *names_or_objs):
        axes_dict = dict((a.name, a) for a in self.get_axes_iter())
        for i in names_or_objs:
            if isinstance(i, str):
                i = axes_dict[i]
            yield i

    def get_counter_from_fullname(self, fullname):
        # looking for a counter with a fullname ([master_controller:]controller:name)
        try:
            controller_fullname, _, _ = fullname.rpartition(":")
        except ValueError:
            raise AttributeError(fullname)
        else:
            for cnt in self.get_counters_iter():
                try:
                    if cnt.fullname == fullname:
                        return cnt
                except AttributeError:
                    continue
            else:
                raise AttributeError(fullname)
