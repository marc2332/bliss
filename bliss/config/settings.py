# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from contextlib import contextmanager
import weakref
import pickle
import keyword
import re
import reprlib

import numpy

from .conductor import client
from bliss.common.utils import Null
from bliss import setup_globals
from tabulate import tabulate


class InvalidValue(Null):
    def __str__(self):
        raise ValueError

    def __repr__(self):
        return "#ERR"


class DefaultValue:
    def __init__(self, wrapped_value):
        self.__value = wrapped_value

    @property
    def value(self):
        return self.__value


def boolify(s, **keys):
    if s in ("True", "true"):
        return True
    if s in ("False", "false"):
        return False
    raise ValueError("Not Boolean Value!")


def auto_coerce_from_redis(s):
    """Convert variable to a new type from the str representation"""
    if s is None:
        return None
    # Default is unicode string
    try:
        if isinstance(s, bytes):
            s = s.decode()
    # Pickled data fails at first byte
    except UnicodeDecodeError:
        pass
    # Cast to standard types
    for caster in (boolify, int, float):
        try:
            return caster(s)
        except (ValueError, TypeError):
            pass
    return s


def pickle_loads(var):
    if var is None:
        return None
    try:
        return pickle.loads(var)
    except Exception:
        return InvalidValue()


def get_redis_connection():
    return client.get_redis_connection(db=0)


def ttl_func(cnx, name, value=-1):
    if value is None:
        return cnx.persist(name)
    elif value is -1:
        return cnx.ttl(name)
    else:
        return cnx.expire(name, value)


def read_decorator(func):
    def _read(self, *args, **keys):
        value = func(self, *args, **keys)
        if self._read_type_conversion:
            if isinstance(value, list):
                value = [self._read_type_conversion(x) for x in value]
            elif isinstance(value, dict):
                for k, v in value.items():
                    value[k] = self._read_type_conversion(v)
                if hasattr(self, "default_values") and isinstance(
                    self.default_values, dict
                ):
                    tmp = dict(self._default_values)
                    tmp.update(value)
                    value = tmp
            else:
                if isinstance(value, DefaultValue):
                    value = value.value
                elif value is not None:
                    value = self._read_type_conversion(value)
        if value is None:
            if hasattr(self, "_default_value"):
                value = self._default_value
            elif hasattr(self, "_default_values") and hasattr(
                self._default_values, "get"
            ):
                value = self._default_values.get(args[0])
        return value

    return _read


def write_decorator_dict(func):
    def _write(self, values, **keys):
        if self._write_type_conversion:
            if not isinstance(values, dict) and values is not None:
                raise TypeError("can only be dict")

            if values is not None:
                new_dict = dict()
                for k, v in values.items():
                    new_dict[k] = self._write_type_conversion(v)
                values = new_dict
        return func(self, values, **keys)

    return _write


def write_decorator_multiple(func):
    def _write(self, values, **keys):
        if self._write_type_conversion:
            if (
                not isinstance(values, (list, tuple, numpy.ndarray))
                and values is not None
            ):
                raise TypeError("Can only be tuple, list or numpy array")
            if values is not None:
                values = [self._write_type_conversion(x) for x in values]
        return func(self, values, **keys)

    return _write


def write_decorator(func):
    def _write(self, value, **keys):
        if self._write_type_conversion and value is not None:
            value = self._write_type_conversion(value)
        return func(self, value, **keys)

    return _write


def scan(match="*", count=1000, connection=None):
    if connection is None:
        connection = get_redis_connection()
    cursor = 0
    while 1:
        cursor, values = connection.scan(cursor=cursor, match=match, count=count)
        for val in values:
            yield val.decode()
        if int(cursor) == 0:
            break


def _get_connection(setting_object):
    """
    Return the connection of a setting_object
    """
    if isinstance(setting_object, Struct):
        return setting_object._proxy._cnx
    elif isinstance(setting_object, (SimpleSetting, QueueSetting, BaseHashSetting)):
        return setting_object._cnx
    else:
        raise TypeError(
            f"Setting object should be one of: Struct, SimpleSetting, QueueSetting or HashSetting instead of {setting_object!r}"
        )


def _set_connection(setting_object, new_cnx):
    """
    change the connection of a setting_object
    and return the previous connection
    """
    if isinstance(setting_object, Struct):
        cnx = setting_object._proxy._cnx
        setting_object._proxy._cnx = new_cnx
    elif isinstance(setting_object, (SimpleSetting, QueueSetting, BaseHashSetting)):
        cnx = setting_object._cnx
        setting_object._cnx = new_cnx
    else:
        raise TypeError(
            f"Setting object should be one of: Struct, SimpleSetting, QueueSetting or HashSetting instead of {setting_object!r}"
        )
    return cnx


@contextmanager
def pipeline(*settings):
    """
    Contextmanager which create a redis pipeline to group redis commands
    on settings.

    IN CASE OF you execute the pipeline, it will return raw database values
    (byte strings).
    """
    first_settings = settings[0]
    cnx = _get_connection(first_settings)()
    # check they have the same connection
    for s in settings[1:]:
        if _get_connection(s)() != cnx:
            raise RuntimeError("Cannot groupe redis commands in a pipeline")

    pipeline = cnx.pipeline()
    try:
        # replace settings connection with the pipeline
        previous_cnx = [_set_connection(s, weakref.ref(pipeline)) for s in settings]
        yield pipeline
    finally:
        [_set_connection(s, c) for c, s in zip(previous_cnx, settings)]
        pipeline.execute()


class SimpleSetting:
    """
    Class to manage a setting that is stored as a string on Redis
    """

    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
        default_value=None,
    ):
        if connection is None:
            connection = get_redis_connection()
        self._cnx = weakref.ref(connection)
        self._name = name
        self._read_type_conversion = read_type_conversion
        self._write_type_conversion = write_type_conversion
        self._default_value = default_value

    @property
    def name(self):
        return self._name

    @read_decorator
    def get(self):
        cnx = self._cnx()
        value = cnx.get(self._name)
        return value

    @write_decorator
    def set(self, value):
        cnx = self._cnx()
        cnx.set(self._name, value)

    def ttl(self, value=-1):
        return ttl_func(self._cnx(), self._name, value)

    def clear(self):
        cnx = self._cnx()
        cnx.delete(self._name)

    def __add__(self, other):
        value = self.get()
        if isinstance(other, SimpleSetting):
            other = other.get()
        return value + other

    def __iadd__(self, other):
        cnx = self._cnx()
        if cnx is not None:
            if isinstance(other, int):
                if other == 1:
                    cnx.incr(self._name)
                else:
                    cnx.incrby(self._name, other)
            elif isinstance(other, float):
                cnx.incrbyfloat(self._name, other)
            else:
                cnx.append(self._name, other)
            return self

    def __isub__(self, other):
        if isinstance(other, str):
            raise TypeError(
                "unsupported operand type(s) for -=: %s" % type(other).__name__
            )
        return self.__iadd__(-other)

    def __getitem__(self, ran):
        cnx = self._cnx()
        if cnx is not None:
            step = None
            if isinstance(ran, slice):
                i, j = ran.start, ran.stop
                step = ran.step
            elif isinstance(ran, int):
                i = j = ran
            else:
                raise TypeError("indices must be integers")

            value = cnx.getrange(self._name, i, j)
            if step is not None:
                value = value[0:-1:step]
            return value

    def __repr__(self):
        cnx = self._cnx()
        value = cnx.get(self._name)
        return "<SimpleSetting name=%s value=%s>" % (self._name, value)


class SimpleSettingProp:
    """
    A python's property implementation for SimpleSetting
    To be used inside user defined classes
    """

    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
        default_value=None,
        use_object_name=True,
    ):
        self._name = name
        self._cnx = connection or get_redis_connection()
        self._read_type_conversion = read_type_conversion
        self._write_type_conversion = write_type_conversion
        self._default_value = default_value
        self._use_object_name = use_object_name

    @property
    def name(self):
        return self._name

    def __get__(self, obj, type=None):
        if self._use_object_name:
            name = obj.name + ":" + self._name
        else:
            name = self._name
        return SimpleSetting(
            name,
            self._cnx,
            self._read_type_conversion,
            self._write_type_conversion,
            self._default_value,
        )

    def __set__(self, obj, value):
        if isinstance(value, SimpleSetting):
            return

        if self._use_object_name:
            name = obj.name + ":" + self._name
        else:
            name = self._name

        if value is None:
            self._cnx.delete(name)
        else:
            if self._write_type_conversion:
                value = self._write_type_conversion(value)
            self._cnx.set(name, value)


class QueueSetting:
    """
    Class to manage a setting that is stored as a list on Redis
    """

    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
    ):
        if connection is None:
            connection = get_redis_connection()
        self._cnx = weakref.ref(connection)
        self._name = name
        self._read_type_conversion = read_type_conversion
        self._write_type_conversion = write_type_conversion

    @property
    def name(self):
        return self._name

    @read_decorator
    def get(self, first=0, last=-1, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        if first == last:
            l = cnx.lindex(self._name, first)
        else:
            if last != -1:
                last -= 1
            l = cnx.lrange(self._name, first, last)
        return l

    @write_decorator
    def append(self, value, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        return cnx.rpush(self._name, value)

    def clear(self, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        cnx.delete(self._name)

    @write_decorator
    def prepend(self, value, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        return cnx.lpush(self._name, value)

    @write_decorator_multiple
    def extend(self, values, cnx=None):
        cnx = self._cnx()
        return cnx.rpush(self._name, *values)

    @write_decorator
    def remove(self, value, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        cnx.lrem(self._name, 0, value)

    @write_decorator_multiple
    def set(self, values, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        cnx.delete(self._name)
        if values is not None:
            cnx.rpush(self._name, *values)

    @write_decorator
    def set_item(self, value, pos=0, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        cnx.lset(self._name, pos, value)

    @read_decorator
    def pop_front(self, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        value = cnx.lpop(self._name)
        if self._read_type_conversion:
            value = self._read_type_conversion(value)
        return value

    @read_decorator
    def pop_back(self, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        value = cnx.rpop(self._name)
        if self._read_type_conversion:
            value = self._read_type_conversion(value)
        return value

    def ttl(self, value=-1, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        return ttl_func(cnx, self._name, value)

    def __len__(self, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        return cnx.llen(self._name)

    def __repr__(self, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        value = cnx.lrange(self._name, 0, -1)
        return "<QueueSetting name=%s value=%s>" % (self._name, value)

    def __iadd__(self, other, cnx=None):
        self.extend(other, cnx)
        return self

    def __getitem__(self, ran, cnx=None):
        if isinstance(ran, slice):
            i = ran.start is not None and ran.start or 0
            j = ran.stop is not None and ran.stop or -1
        elif isinstance(ran, int):
            i = j = ran
        else:
            raise TypeError("indices must be integers")
        value = self.get(first=i, last=j, cnx=cnx)
        if value is None:
            raise IndexError
        else:
            return value

    def __iter__(self, cnx=None):
        if cnx is None:
            cnx = self._cnx()
        lsize = cnx.llen(self._name)
        for first in range(0, lsize, 1024):
            last = first + 1024
            if last >= lsize:
                last = -1
            for value in self.get(first, last):
                yield value

    def __setitem__(self, ran, value, cnx=None):
        if isinstance(ran, slice):
            for i, v in zip(range(ran.start, ran.stop), value):
                self.set_item(v, pos=i, cnx=cnx)
        elif isinstance(ran, int):
            self.set_item(value, pos=ran, cnx=cnx)
        else:
            raise TypeError("indices must be integers")
        return self


class QueueSettingProp:
    """
    A python's property implementation for QueueSetting
    To be used inside user defined classes
    """

    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
        use_object_name=True,
    ):
        self._name = name
        self._cnx = connection or get_redis_connection()
        self._read_type_conversion = read_type_conversion
        self._write_type_conversion = write_type_conversion
        self._use_object_name = use_object_name

    @property
    def name(self):
        return self._name

    def __get__(self, obj, type=None):
        if self._use_object_name:
            name = obj.name + ":" + self._name
        else:
            name = self._name

        return QueueSetting(
            name, self._cnx, self._read_type_conversion, self._write_type_conversion
        )

    def __set__(self, obj, values):
        if isinstance(values, QueueSetting):
            return

        if self._use_object_name:
            name = obj.name + ":" + self._name
        else:
            name = self._name

        proxy = QueueSetting(
            name, self._cnx, self._read_type_conversion, self._write_type_conversion
        )
        proxy.set(values)


class BaseHashSetting:
    """
    A Setting stored as a key,value pair in Redis

    Args:
        name: name of the BaseHashSetting (used on Redis)
        connection: Redis connection object
            read_type_conversion: conversion of data applyed
                after reading
            write_type_conversion: conversion of data applyed
                before writing
    """

    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
    ):
        if connection is None:
            connection = get_redis_connection()
        self._cnx = weakref.ref(connection)
        self._name = name
        self._read_type_conversion = read_type_conversion
        self._write_type_conversion = write_type_conversion

    @property
    def name(self):
        return self._name

    def __repr__(self):
        value = self.get_all()
        return f"<{type(self).__name__} name=%s value=%s>" % (self._name, value)

    def __delitem__(self, key):
        cnx = self._cnx()
        cnx.hdel(self._name, key)

    def __len__(self):
        cnx = self._cnx()
        return cnx.hlen(self._name)

    def ttl(self, value=-1):
        return ttl_func(self._cnx(), self._name, value)

    def raw_get(self, *keys):
        cnx = self._cnx()
        return cnx.hget(self._name, *keys)

    @read_decorator
    def get(self, key, default=None):
        v = self.raw_get(key)
        if v is None:
            v = DefaultValue(default)
        return v

    def _raw_get_all(self):
        cnx = self._cnx()
        return cnx.hgetall(self._name)

    def get_all(self):
        all_dict = dict()
        for k, raw_v in self._raw_get_all().items():
            k = k.decode()
            v = self._read_type_conversion(raw_v)
            if isinstance(v, InvalidValue):
                raise ValueError(
                    "%s: Invalid value '%s` (cannot deserialize %r)"
                    % (self._name, k, raw_v)
                )
            all_dict[k] = v
        return all_dict

    @read_decorator
    def pop(self, key, default=Null()):
        cnx = self._cnx().pipeline()
        cnx.hget(self._name, key)
        cnx.hdel(self._name, key)
        (value, worked) = cnx.execute()
        if not worked:
            if isinstance(default, Null):
                raise KeyError(key)
            else:
                value = default
        return value

    def remove(self, *keys):
        cnx = self._cnx()
        cnx.hdel(self._name, *keys)

    def clear(self):
        cnx = self._cnx()
        cnx.delete(self._name)

    def copy(self):
        return self.get()

    @write_decorator_dict
    def set(self, values):
        cnx = self._cnx()
        cnx.delete(self._name)
        if values is not None:
            cnx.hmset(self._name, values)

    @write_decorator_dict
    def update(self, values):
        cnx = self._cnx()
        if values:
            cnx.hmset(self._name, values)

    @read_decorator
    def fromkeys(self, *keys):
        cnx = self._cnx()
        return cnx.hmget(self._name, *keys)

    def has_key(self, key):
        cnx = self._cnx()
        return cnx.hexists(self._name, key)

    def keys(self):
        for k, v in self.items():
            yield k

    def values(self):
        for k, v in self.items():
            yield v

    def items(self):
        cnx = self._cnx()
        next_id = 0
        seen_keys = set()
        while True:
            next_id, pd = cnx.hscan(self._name, next_id)
            for k, v in pd.items():
                # Add key conversion
                k = k.decode()
                if self._read_type_conversion:
                    v = self._read_type_conversion(v)
                seen_keys.add(k)
                yield k, v
            if not next_id or next_id is "0":
                break

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        cnx = self._cnx()
        if value is None:
            cnx.hdel(self._name, key)
            return
        if self._write_type_conversion:
            value = self._write_type_conversion(value)
        cnx.hset(self._name, key, value)

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False


class HashSetting(BaseHashSetting):
    """
    A Setting stored as a key,value pair in Redis
    with a default_value dictionary to serve as a callback
    when elements lookup fails

    Args:
        name: name of the HashSetting (used on Redis)
        connection: Redis connection object
            read_type_conversion: conversion of data applyed
                after reading
            write_type_conversion: conversion of data applyed
                before writing
    kwargs:
        default_values: dictionary of default values retrieved
            on fallback
    """

    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
        default_values={},
    ):
        super().__init__(
            name,
            connection=connection,
            read_type_conversion=read_type_conversion,
            write_type_conversion=write_type_conversion,
        )
        self._default_values = default_values

    @read_decorator
    def get(self, key, default=None):
        v = super().raw_get(key)
        if v is None:
            v = DefaultValue(default)
        return v

    def has_key(self, key):
        return super().has_key(key) or key in self._default_values

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            if key not in self._default_values:
                raise KeyError(key)
        return value

    def get_all(self):
        all_dict = dict(self._default_values)
        for k, raw_v in self._raw_get_all().items():
            k = k.decode()
            v = self._read_type_conversion(raw_v)
            if isinstance(v, InvalidValue):
                raise ValueError(
                    "%s: Invalid value '%s` (cannot deserialize %r)"
                    % (self._name, k, raw_v)
                )
            all_dict[k] = v
        return all_dict

    def items(self):
        cnx = self._cnx()
        next_id = 0
        seen_keys = set()
        while True:
            next_id, pd = cnx.hscan(self._name, next_id)
            for k, v in pd.items():
                # Add key conversion
                k = k.decode()
                if self._read_type_conversion:
                    v = self._read_type_conversion(v)
                seen_keys.add(k)
                yield k, v
            if not next_id or next_id is "0":
                break

        for k, v in self._default_values.items():
            if k in seen_keys:
                continue
            yield k, v


class HashSettingProp:
    def __init__(
        self,
        name,
        connection=None,
        read_type_conversion=auto_coerce_from_redis,
        write_type_conversion=str,
        default_values={},
        use_object_name=True,
    ):
        self._name = name
        self._cnx = connection or get_redis_connection()
        self._read_type_conversion = read_type_conversion
        self._write_type_conversion = write_type_conversion
        self._default_values = default_values
        self._use_object_name = use_object_name

    @property
    def name(self):
        return self._name

    def __get__(self, obj, type=None):
        if self._use_object_name:
            name = obj.name + ":" + self._name
        else:
            name = self._name

        return HashSetting(
            name,
            self._cnx,
            self._read_type_conversion,
            self._write_type_conversion,
            self._default_values,
        )

    def __set__(self, obj, values):
        if self._use_object_name:
            name = obj.name + ":" + self._name
        else:
            name = self._name

        if isinstance(values, HashSetting):
            return

        proxy = HashSetting(
            name,
            self._cnx,
            self._read_type_conversion,
            self._write_type_conversion,
            self._default_values,
        )
        proxy.set(values)

    def get_proxy(self):
        return HashSetting(
            self._name,
            self._cnx,
            self._read_type_conversion,
            self._write_type_conversion,
            self._default_values,
        )


# helper


def _change_to_obj_marshalling(keys):
    read_type_conversion = keys.pop("read_type_conversion", pickle_loads)
    write_type_conversion = keys.pop("write_type_conversion", pickle.dumps)
    keys.update(
        {
            "read_type_conversion": read_type_conversion,
            "write_type_conversion": write_type_conversion,
        }
    )


class HashObjSetting(HashSetting):
    """
    Class to manage a setting that is stored as a dictionary on redis
    where values of the dictionary are pickled
    """

    def __init__(self, name, **keys):
        _change_to_obj_marshalling(keys)
        super().__init__(name, **keys)


class HashObjSettingProp(HashSettingProp):
    """
    A python's property implementation for HashObjSetting
    To be used inside user defined classes
    """

    def __init__(self, name, **keys):
        _change_to_obj_marshalling(keys)
        super().__init__(name, **keys)


class QueueObjSetting(QueueSetting):
    """
    Class to manage a setting that is stored as a list on redis
    where values of the list are pickled
    """

    def __init__(self, name, **keys):
        _change_to_obj_marshalling(keys)
        super().__init__(name, **keys)


class QueueObjSettingProp(QueueSettingProp):
    """
    A python's property implementation for QueueObjSetting
    To be used inside user defined classes
    """

    def __init__(self, name, **keys):
        _change_to_obj_marshalling(keys)
        super().__init__(name, **keys)


class SimpleObjSetting(SimpleSetting):
    """
    Class to manage a setting that is stored as pickled object
    on redis
    """

    def __init__(self, name, **keys):
        _change_to_obj_marshalling(keys)
        super().__init__(name, **keys)


class SimpleObjSettingProp(SimpleSettingProp):
    """
    A python's property implementation for SimpleObjSetting
    To be used inside user defined classes
    """

    def __init__(self, name, **keys):
        _change_to_obj_marshalling(keys)
        super().__init__(name, **keys)


class Struct:
    def __init__(self, name, **keys):
        self._proxy = HashSetting(name, **keys)

    def __dir__(self):
        return self._proxy.keys()

    def __repr__(self):
        return "<Struct with attributes: %s>" % self._proxy.keys()

    def __getattribute__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        else:
            return self._proxy.get(name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return object.__setattr__(self, name, value)
        else:
            self._proxy[name] = value

    def __delattr__(self, name):
        if name.startswith("_"):
            return object.__delattr__(self, name)
        else:
            self._proxy.remove(name)


class ParametersType(type):
    """
    Created classes have access to a limited number of
    attributes defined inside SLOTS class attribute.
    Also created classes are unique every time, so we
    can use class.__dict__ with Python descriptors
    and be sure that those are not shared beetween
    two different instances
    """

    def __call__(cls, *args, **kwargs):
        class_dict = {"__slots__": tuple(cls.SLOTS), "SLOTS": cls.SLOTS}
        new_cls = type(cls.__name__, (cls,), class_dict)
        return type.__call__(new_cls, *args, **kwargs)

    def __new__(cls, name, bases, attrs):
        attrs["__slots__"] = tuple(attrs["SLOTS"])
        return type.__new__(cls, name, bases, attrs)


class ParamDescriptor:
    """
    Used to link python global objects
    If necessary It will create an entry on redis under
    parameters:objects:name
    """

    OBJECT_PREFIX = "parameters:object:"

    def __init__(self, proxy, name, value, assign=True):
        self.proxy = proxy
        self.name = name
        if assign:
            self.assign(value)

    def assign(self, value):
        """
        if the value is a global defined object it will create a link
        to that object inside the ParamDescriptor and the link will
        be stored inside redis in this way:'parameters:object:name'
        otherwise the value will be stored normally
        """
        if hasattr(value, "name") and hasattr(setup_globals, value.name):
            value = "%s%s" % (ParamDescriptor.OBJECT_PREFIX, value.name)
        try:
            self.proxy[self.name] = value
        except Exception:
            raise ValueError("%s.%s: cannot set value" % (self.proxy._name, self.name))

    def __get__(self, obj, obj_type):
        value = self.proxy[self.name]
        if isinstance(value, str) and value.startswith(ParamDescriptor.OBJECT_PREFIX):
            value = value[len(ParamDescriptor.OBJECT_PREFIX) :]
            return getattr(setup_globals, value)
        return value

    def __set__(self, obj, value):
        return self.assign(value)

    def __delete__(self, *args):
        del self.proxy[self.name]


class ParamDescriptorWithDefault:
    """
    Like ParamDescriptor but It contains two references on redis:
    proxy and proxy_default.
    If the proxy key doesn't exists it returns the value of the default
    """

    OBJECT_PREFIX = "parameters:object:"

    def __init__(self, proxy, proxy_default, name, value, assign=True):
        self.proxy = proxy
        self.proxy_default = proxy_default
        self.name = name  # name of parameter
        if assign:
            self.assign(value)

    def assign(self, value):
        """
        if the value is a global defined object it will create a link
        to that object inside the ParamDescriptor and the link will
        be stored inside redis in this way:'parameters:object:name'
        otherwise the value will be stored normally
        """
        if hasattr(value, "name") and hasattr(setup_globals, value.name):
            value = "%s%s" % (ParamDescriptor.OBJECT_PREFIX, value.name)
        try:
            self.proxy[self.name] = value
        except Exception:
            raise ValueError("%s.%s: cannot set value" % (self.proxy._name, self.name))

    def __get__(self, obj, obj_type):
        try:
            value = self.proxy[self.name]
        except KeyError:
            # getting from default
            value = self.proxy_default[self.name]
        if isinstance(value, str) and value.startswith(
            ParamDescriptorWithDefault.OBJECT_PREFIX
        ):
            value = value[len(ParamDescriptorWithDefault.OBJECT_PREFIX) :]
            try:
                return getattr(setup_globals, value)
            except AttributeError:
                raise AttributeError(
                    f"The object '{self.name}' is not "
                    "found in the globals: Be sure to"
                    " work inside the right session"
                )

        if value == "None":
            # Manages the python None value stored in Redis as a string
            value = None
        return value

    def __set__(self, obj, value):
        return self.assign(value)

    def __delete__(self, *args):
        del self.proxy[self.name]
        del self.proxy_default[self.name]


class ParametersWardrobe(metaclass=ParametersType):
    DESCRIPTOR = ParamDescriptorWithDefault
    SLOTS = [
        "_proxy",
        "_proxy_default",
        "_sets",
        "_wardr_name",
        "_property_attributes",
        "_not_removable",
    ]

    def __init__(
        self,
        name,
        default_values=None,
        property_attributes=None,
        not_removable=None,
        **keys,
    ):
        """
        ParametersWardrobe is a convenient way of storing parameters
        tipically to be passed to a function or procedure.
        The advantage is that you can easily create new sets
        in which you can modify only some parameters and
        keep the rest to default.
        Is like having different dresses for different purposes and
        changing them easily.

        All Sets are stored in Redis, you will have:
        * A list of Names with the chosen key parameters:name
        * Hash types Sets with key 'parameters:wardrobename:setname' one
            for each set

        Args:
            name: the name of the ParametersWardrobe

        kwargs:
            default_values: dict of default values
            property_attributes: iterable with attribute names implemented
                                 internally as properties (for subclassing)
                                 Those attribute are computed on the fly
            not_removable: list of not removable keys, for example could be
                           default values (that usually should not be removed)
            **keys: other key,value pairs will be directly passed to Redis proxy
        """
        if not default_values:
            default_values = {}
        if not property_attributes:
            property_attributes = []
        if not not_removable:
            not_removable = []

        # different set names are stored in a queue where
        # the first item is the currently used one
        self._sets = QueueSetting("parameters:%s" % name)
        self._wardr_name = name  # name of the ParametersWardrobe
        self._property_attributes = property_attributes  # list of property_attributes
        self._not_removable = not_removable

        if "default" not in self._sets:
            # if it is a new created one, append default set
            self._sets.append("default")

        # creates the two needed proxies
        self._proxy = BaseHashSetting(self._hash("default"), **keys)
        self._proxy_default = BaseHashSetting(self._hash("default"), **keys)

        # Managing default written to proxy_default
        for name, value in default_values.items():
            self.add(name, value)

        self.switch(self._sets[0])

    def _hash(self, name):
        """
        Helper for extracting the redis name of parameter set
        """
        return "parameters:%s:%s" % (self._wardr_name, name)

    def __dir__(self):
        keys_proxy = {x for x in self._proxy.keys() if not x.startswith("_")}
        keys_proxy_default = {
            x for x in self._proxy_default.keys() if not x.startswith("_")
        }
        return list(keys_proxy.union(keys_proxy_default)) + [
            "add",
            "remove",
            "switch",
            "configs",
            "to_dict",
            "from_dict",
            "freeze",
            "show_table",
        ]

    def to_dict(self):
        """
        Retrieve all parameters inside a set in a dict form
        If a parameter is not present inside the set, the
        default will be taken, property (computed) attributes are included.

        Returns:
            dictionary with (parameter,value) pairs
        """
        return {
            **self._get_redis_single_set("default"),
            **self._get_redis_single_set(self._sets[0]),
            **{attr: getattr(self, attr) for attr in self._property_attributes},
        }
        return all_params

    def from_dict(self, d):
        """
        Updates the current set of values from a dictionary.

        You should provide a dictionary with the same attribute names as
        current existing inside the ParametersWardrobe you want to update.
        Property attributes should not be given.

        Raises:
            TypeError: Dictionary empty or attribute different from current ParameterWardrobe attributes
        """
        if (
            d
            and set(self._get_redis_single_set("default").keys()).difference(d.keys())
            == set()
        ):
            # if dictionary not empty and attribute names are same as currente set of parameters
            for name, value in d.items():
                setattr(
                    self.__class__,
                    name,
                    self.DESCRIPTOR(
                        self._proxy, self._proxy_default, name, value, True
                    ),
                )
        else:
            raise TypeError(
                f"Dictionary empty or attribute different from current {type(self).__name__} attributes"
            )

    def show_table(self):
        """
        Shows all data inside ParameterWardrobe different sets

        - Property attributes are identified with an # (hash)
        - parameters taken from default are identified with an * (asterisk)
        - parameters with a name starting with underscore are omitted
        """

        redis_data = self._get_redis_all_sets()

        column_names = self._sets
        column_repr = (
            self._sets[0] + " (SELECTED)",
            *self._sets[1:],
        )  # adds SELECTED to first name
        row_names = (
            # gets attribute names, remove underscore attributes
            *(k for k in redis_data["default"].keys() if not k.startswith("_")),
            *(k for k in self._property_attributes if not k.startswith("_")),
        )

        # data creation
        data = list()
        data.append(column_repr)  # set names on first row
        for row_name in sorted(row_names):
            row_data = []
            row_data.append(row_name)
            for col in column_names:
                if row_name in self._property_attributes:
                    cell = "# " + str(getattr(self, row_name))
                elif row_name in redis_data[col].keys():
                    cell = str(redis_data[col][row_name])
                else:
                    cell = "* " + str(redis_data["default"][row_name])

                row_data.append(cell)
            data.append(row_data)

        print(
            """* asterisks means value not stored in database (default is taken)\n# hash means a computed attribute (property)\n\n"""
        )
        print(tabulate(data, headers="firstrow", stralign="right"))

    def __repr__(self):
        return self._repr(self.to_dict())

    def _repr(self, d):
        rep_str = f"Parameters ({self._sets[0]}) - " + " ".join(self._sets[1:]) + "\n\n"
        max_len = max((0,) + tuple(len(x) for x in d.keys()))
        str_format = "  .%-" + "%ds" % max_len + " = %r\n"
        for key, value in sorted(d.items()):
            if key.startswith("_"):
                continue
            rep_str += str_format % (key, value)
        return rep_str

    def _get_redis_single_set(self, name):
        """
        Retrieve a single set of parameters
        """
        try:
            name_backup = self._proxy._name
            if name in self._sets:
                self._proxy._name = self._hash(name)
                return self._proxy.get_all()
            return {}
        finally:
            self._proxy._name = name_backup

    def _get_redis_all_sets(self):
        """
        Retrieve all parameters of all sets from redis as dict of dicts
        """
        params_all = {}

        for config in self._sets:
            params = self._get_redis_single_set(config)
            params_all[config] = {**params}
        return params_all

    def _get_set(self, name):
        """
        Retrieve all parameters inside a set
        Taking from default if not present inside the set
        Property are included

        Returns:
            dictionary with (parameter,value) pairs
        """
        return {
            **self._get_redis_single_set("default"),
            **self._get_redis_single_set(self._sets[0]),
            **self._property_attributes,
        }

    def add(self, name, value=None):
        """
        Adds a parameter to all sets storing the value only on
        'default' parameter

        Args:
            name: name of the parameter (Python attribute) accessible
                  with . dot notation
            value: value of the parameter, None is passed as default
                   if omitted

        Raises:
            NameError: Existing attribute name
        """
        if name in self._property_attributes:
            raise NameError(f"Existing computed property with this name: {name}")

        self.DESCRIPTOR(
            self._proxy_default,
            self._proxy_default,
            name,
            value if value else "None",
            True,
        )
        self._populate(name)

    def _populate(self, name, value=None):
        setattr(
            self.__class__,
            name,
            self.DESCRIPTOR(self._proxy, self._proxy_default, name, value, bool(value)),
        )

    def freeze(self):
        """
        Freezing values for current set: all default taken values will be
        written inside the set so changes on 'default' set will not cause
        change on the current set.

        If you later add another parameter this will still refer to 'default'
        so you will need to freeze again
        """
        redis_params = {
            **self._get_redis_single_set("default"),
            **self._get_redis_single_set(self._sets[0]),
        }
        for name, value in redis_params.items():
            setattr(
                self.__class__,
                name,
                self.DESCRIPTOR(self._proxy, self._proxy_default, name, value, True),
            )

    def remove(self, param):
        """
        Remove a parameter or a set of parameters from all sets

        Args:
            param: name of a set to remove a whole set
                   .name of a parameter to remove a parameter from all sets

        Examples:
            >>> p = ParametersWardrobe('p')

            >>> p.add('head', 'hat')

            >>> p.switch('casual')

            >>> p.remove('.head')  # with dot to remove a parameter

            >>> p.remove('casual') # without dot to remove a complete set
        """

        if param.startswith("."):
            # removing a parameter from every set
            param = param[1:]
            if param in self._not_removable or param in self._property_attributes:
                raise AttributeError("Can't remove attribute")
            for param_set in self._sets:
                pr = BaseHashSetting(self._hash(param_set))
                pr.remove(param)
        elif param != "default" and param in self._sets:
            # removing a set of parameters
            pr = BaseHashSetting(self._hash(param))
            pr.clear()
            self._sets.remove(param)  # removing from Queue
        else:
            raise NameError(f"Can't remove {param}")

    def switch(self, name, copy=None):
        """
        Switches to a new set of parameters.

        Values of parameters will be retrieved from redis (if existent).
        In case of a non existing set name, a new set of parameters will
        be created and It will be populated with name,value pairs from
        the current 'default' set.
        This is not a copy, but only a reference, so changes on default
        will reflect to the new set.

        The value of an attribute is stored in Redis after an assigment
        operation (also if assigned value is same as default).

        To freeze the full set you can use the 'freeze' method.

        Args:
            name: name of set of parameters to switch to
            copy: name of set of parameters to copy for initialization

        Returns:
            None
        """
        for key, value in dict(self.__class__.__dict__).items():
            if isinstance(value, self.DESCRIPTOR):
                delattr(self.__class__, key)

        # removing and prepending the name so it will be the first
        self._sets.remove(name)
        self._sets.prepend(name)

        self._proxy._name = self._hash(name)

        # adding default
        for key in self._proxy_default.keys():
            self._populate(key)

        # copy values from existing set
        if copy and copy in self._sets:
            copy_params = self._get_redis_single_set(copy)
            for key, value in copy_params.items():
                self._populate(key, value=value)

        for key in self._proxy.keys():
            self._populate(key)

    @property
    def configs(self):
        """
        Returns:
            A list containing all sets names
        """
        return list(self._sets)


if __name__ == "__main__":

    class A(object):
        x = SimpleSettingProp("counter")
        y = SimpleObjSettingProp("obj")
        q = QueueSettingProp("seb")
        ol = QueueObjSettingProp("seb-list")
        h = HashSettingProp("seb-hash")
        oh = HashObjSettingProp("seb-hash-object")

        def __init__(self, name):
            self.name = name

    a = A("m0")
    p = Struct("optics:zap:params")
