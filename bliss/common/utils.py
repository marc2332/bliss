# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os, sys
import traceback
import inspect
import gevent
import types
import itertools
import functools
import numpy
import sys
import copy
import collections.abc

from bliss.common.event import saferef


class ErrorWithTraceback:
    def __init__(self, error_txt="!ERR"):
        self._ERR = error_txt
        self.exc_info = None

    def __str__(self):
        return self._ERR


class WrappedMethod(object):
    def __init__(self, control, method_name):
        self.method_name = method_name
        self.control = control

    def __call__(self, this, *args, **kwargs):
        return getattr(self.control, self.method_name)(*args, **kwargs)


def wrap_methods(from_object, target_object):
    for name in dir(from_object):
        if inspect.ismethod(getattr(from_object, name)):
            if hasattr(target_object, name) and inspect.ismethod(
                getattr(target_object, name)
            ):
                continue
            setattr(
                target_object,
                name,
                types.MethodType(WrappedMethod(from_object, name), target_object),
            )


def add_property(inst, name, method):
    cls = type(inst)
    module = cls.__module__
    if not hasattr(cls, "__perinstance"):
        cls = type(cls.__name__, (cls,), {})
        cls.__perinstance = True
        cls.__module__ = module
        inst.__class__ = cls
    setattr(cls, name, property(method))


def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return zip(*[iter(iterable)] * n)


def flatten(seq):
    """list -> list                                                                                                                                                                           
    return a flattend list from an abitrarily nested list                                                                                                                                     
    """
    if not seq:
        return seq
    if not isinstance(seq[0], list):
        return [seq[0]] + flatten(seq[1:])
    return flatten(seq[0]) + flatten(seq[1:])


def all_equal(iterable):
    g = itertools.groupby(iterable)
    return next(g, True) and not next(g, False)


"""
functions to add custom attributes and commands to an object.
"""


def add_object_method(
    obj, method, pre_call, name=None, args=[], types_info=(None, None)
):

    if name is None:
        name = method.__func__.__name__

    def call(self, *args, **kwargs):
        if callable(pre_call):
            pre_call(self, *args, **kwargs)
        return method.__func__(method.__self__, *args, **kwargs)

    obj._add_custom_method(
        types.MethodType(
            functools.update_wrapper(functools.partial(call, *([obj] + args)), method),
            obj,
        ),
        name,
        types_info,
    )


def object_method(
    method=None, name=None, args=[], types_info=(None, None), filter=None
):
    """
    Decorator to add a custom method to an object.

    The same as add_object_method but its purpose is to be used as a
    decorator to the controller method which is to be exported as object method.
    
    Returns a method where _object_method_ attribute is filled with a dict of elements to characterize it.
    """

    def get_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # We strip the first argument in the signature as it will be the 'self'
        # of the instance to which the method will be attached
        sig = inspect.signature(func)
        sig = sig.replace(parameters=tuple(sig.parameters.values())[1:])
        wrapper.__signature__ = sig

        wrapper._object_method_ = dict(
            name=name, args=args, types_info=types_info, filter=filter
        )
        return wrapper

    if method is None:
        # Passes here if decorator is called with decorator arguments
        def object_method_wrap(func):
            return get_wrapper(func)

        return object_method_wrap
    else:
        # Passes here if the decorator is called without arguments
        return get_wrapper(method)


def object_method_type(
    method=None, name=None, args=[], types_info=(None, None), type=None
):
    def f(x):
        return isinstance(x, type)

    return object_method(
        method=method, name=name, args=args, types_info=types_info, filter=f
    )


def add_object_attribute(
    obj, name=None, fget=None, fset=None, args=[], type_info=None, filter=None
):
    obj._add_custom_attribute(name, fget, fset, type_info)


"""
decorators for set/get methods to access to custom attributes
"""


def object_attribute_type_get(
    get_method=None, name=None, args=[], type_info=None, type=None
):
    def f(x):
        return isinstance(x, type)

    return object_attribute_get(
        get_method=get_method, name=name, args=args, type_info=type_info, filter=f
    )


def object_attribute_get(
    get_method=None, name=None, args=[], type_info=None, filter=None
):
    if get_method is None:
        return functools.partial(
            object_attribute_get,
            name=name,
            args=args,
            type_info=type_info,
            filter=filter,
        )

    if name is None:
        name = get_method.__name__
    attr_name = name
    if attr_name.startswith("get_"):
        attr_name = attr_name[4:]  # removes leading "get_"

    get_method._object_method_ = dict(
        name=name, args=args, types_info=("None", type_info), filter=filter
    )

    if not hasattr(get_method, "_object_attribute_"):
        get_method._object_attribute_ = dict()
    get_method._object_attribute_.update(
        name=attr_name, fget=get_method, args=args, type_info=type_info, filter=filter
    )

    return get_method


def object_attribute_type_set(
    set_method=None, name=None, args=[], type_info=None, type=None
):
    def f(x):
        return isinstance(x, type)

    return object_attribute_set(
        set_method=set_method, name=name, args=args, type_info=type_info, filter=f
    )


def object_attribute_set(
    set_method=None, name=None, args=[], type_info=None, filter=None
):
    if set_method is None:
        return functools.partial(
            object_attribute_set,
            name=name,
            args=args,
            type_info=type_info,
            filter=filter,
        )

    if name is None:
        name = set_method.__name__
    attr_name = name
    if attr_name.startswith("set_"):
        attr_name = attr_name[4:]  # removes leading "set_"

    set_method._object_method_ = dict(
        name=name, args=args, types_info=(type_info, "None"), filter=filter
    )

    if not hasattr(set_method, "_object_attribute_"):
        set_method._object_attribute_ = dict()
    set_method._object_attribute_.update(
        name=attr_name, fset=set_method, args=args, type_info=type_info, filter=filter
    )

    return set_method


def set_custom_members(src_obj, target_obj, pre_call=None):
    # Creates custom methods and attributes for <target_obj> object
    # using <src_object> object definitions.
    # Populates __custom_methods_list and __custom_attributes_dict
    # for tango device server.
    for name, member in inspect.getmembers(src_obj):
        # Just fills the list.
        if hasattr(member, "_object_attribute_"):
            attribute_info = dict(member._object_attribute_)
            filter = attribute_info.pop("filter", None)
            if filter is None or filter(target_obj):
                add_object_attribute(target_obj, **member._object_attribute_)

        # For each method of <src_obj>: try to add it as a
        # custom method or as methods to set/get custom
        # attributes.
        try:
            method_info = dict(member._object_method_)
            filter = method_info.pop("filter", None)
            if filter is None or filter(target_obj):
                add_object_method(target_obj, member, pre_call, **method_info)
        except AttributeError:
            pass


def with_custom_members(klass):
    """A class decorator to enable custom attributes and custom methods"""

    def _get_custom_methods(self):
        try:
            return self.__custom_methods_list
        except AttributeError:
            self.__custom_methods_list = []
            return self.__custom_methods_list

    def custom_methods_list(self):
        """ Returns a *copy* of the custom methods """
        return self._get_custom_methods()[:]

    def _add_custom_method(self, method, name, types_info=(None, None)):
        setattr(self, name, method)
        self._get_custom_methods().append((name, types_info))

    def _get_custom_attributes(self):
        try:
            return self.__custom_attributes_dict
        except AttributeError:
            self.__custom_attributes_dict = {}
            return self.__custom_attributes_dict

    def custom_attributes_list(self):
        """
        List of custom attributes defined for this axis.
        Internal usage only
        """
        ad = self._get_custom_attributes()

        # Converts dict into list...
        return [(a_name, ad[a_name][0], ad[a_name][1]) for a_name in ad]

    def _add_custom_attribute(self, name, fget=None, fset=None, type_info=None):
        custom_attrs = self._get_custom_attributes()
        attr_info = custom_attrs.get(name)
        if attr_info:
            orig_type_info, access_mode = attr_info
            if fget and not "r" in access_mode:
                access_mode = "rw"
            if fset and not "w" in access_mode:
                access_mode = "rw"
            assert type_info == orig_type_info, "%s get/set types mismatch" % name
        else:
            access_mode = "r" if fget else ""
            access_mode += "w" if fset else ""
            if fget is None and fset is None:
                raise RuntimeError("impossible case: must have fget or fset...")
        custom_attrs[name] = type_info, access_mode

    klass._get_custom_methods = _get_custom_methods
    klass.custom_methods_list = property(custom_methods_list)
    klass._add_custom_method = _add_custom_method
    klass._get_custom_attributes = _get_custom_attributes
    klass.custom_attributes_list = property(custom_attributes_list)
    klass._add_custom_attribute = _add_custom_attribute

    return klass


class Null(object):
    __slots__ = []

    def __call__(self, *args, **kwargs):
        pass


class StripIt(object):
    """
    Encapsulate object with a short str/repr/format.
    Useful to have in log messages since it only computes the representation
    if the log message is recorded. Example::

        >>> import logging
        >>> logging.basicConfig(level=logging.DEBUG)

        >>> from bliss.common.utils import StripIt

        >>> msg_from_socket = 'Here it is my testament: ' + 50*'bla '
        >>> logging.debug('Received: %s', StripIt(msg_from_socket))
        DEBUG:root:Received: Here it is my testament: bla bla bla bla bla [...]
    """

    __slots__ = "obj", "max_len"

    def __init__(self, obj, max_len=50):
        self.obj = obj
        self.max_len = max_len

    def __strip(self, s):
        max_len = self.max_len
        if len(s) > max_len:
            suffix = " [...]"
            s = s[: max_len - len(suffix)] + suffix
        return s

    def __str__(self):
        return self.__strip(str(self.obj))

    def __repr__(self):
        return self.__strip(repr(self.obj))

    def __format__(self, format_spec):
        return self.__strip(format(self.obj, format_spec))


class periodic_exec(object):
    def __init__(self, period_in_s, func):
        if not callable(func):
            self.func_ref = None
        else:
            self.func_ref = saferef.safe_ref(func)
        self.period = period_in_s
        self.__task = None

    def __enter__(self):
        if self.period > 0 and self.func_ref:
            self.__task = gevent.spawn(self._timer)

    def __exit__(self, *args):
        if self.__task is not None:
            self.__task.kill()

    def _timer(self):
        while True:
            func = self.func_ref()
            if func is None:
                return
            else:
                func()
                del func
                gevent.sleep(self.period)


def safe_get(obj, member, on_error=None, **kwargs):
    try:
        if isinstance(getattr(type(obj), member), property):
            return getattr(obj, member)
        else:
            return getattr(obj, member)(**kwargs)
    except Exception:
        if on_error:
            if isinstance(on_error, ErrorWithTraceback):
                on_error.exc_info = sys.exc_info()
            return on_error


def common_prefix(paths, sep=os.path.sep):
    def allnamesequal(name):
        return all(n == name[0] for n in name[1:])

    bydirectorylevels = zip(*[p.split(sep) for p in paths])
    return sep.join(x[0] for x in itertools.takewhile(allnamesequal, bydirectorylevels))


def human_time_fmt(num, suffix="s"):
    """
    format time second in human readable format
    """
    for unit in ["", "m", "u", "p", "f"]:
        if abs(num) < 1:
            num *= 1000
            continue
        return "%3.3f%s%s" % (num, unit, suffix)


class Statistics(object):
    """
    Calculate statistics from a profiling dictionary
    key == function name
    values == list of tuple (start_time,end_time)
    """

    def __init__(self, profile):
        self._profile = {
            key: numpy.array(values, dtype=numpy.float)
            for key, values in profile.items()
        }

    @property
    def elapsed_time(self):
        """
        elapsed time function
        """
        return {
            key: values[:, 1] - values[:, 0] for key, values in self._profile.items()
        }

    @property
    def min_mean_max_std(self):
        """
        dict with (min, mean, max, std) tuple
        """
        return {
            key: (values.min(), values.mean(), values.max(), values.std())
            for key, values in self.elapsed_time.items()
        }

    def __info__(self):
        # due to recursion import standard here
        from bliss.common import standard

        data = [("func_name", "min", "mean", "max", "std")]

        for key, values in sorted(self.min_mean_max_std.items()):
            data.append(
                (
                    key,
                    human_time_fmt(values[0]),
                    human_time_fmt(values[1]),
                    human_time_fmt(values[2]),
                    values[3],
                )
            )
        return standard._tabulate(data)


class autocomplete_property(property):
    """
    a custom property class that will be added to 
    jedi's ALLOWED_DESCRIPTOR_ACCESS via 
    
    from jedi.evaluate.compiled import access
    access.ALLOWED_DESCRIPTOR_ACCESS += (autocomplete_property,)
    
    in the bliss shell so
    @property  --> not evaluated for autocompletion
    @autocomplete_property  --> evaluated for autocompletion
    
    the @autocomplete_property decorator is especially useful for
    counter namespaces or similar object
    """

    pass


def deep_update(d, u):
    """Do a deep merge of one dict into another.

    This will update d with values in u, but will not delete keys in d
    not found in u at some arbitrary depth of d. That is, u is deeply
    merged into d.

    Args -
      d, u: dicts

    Note: this is destructive to d, but not u.

    Returns: None
    """
    stack = [(d, u)]
    while stack:
        d, u = stack.pop(0)
        for k, v in u.items():
            if not isinstance(v, collections.abc.Mapping):
                # u[k] is not a dict, nothing to merge, so just set it,
                # regardless if d[k] *was* a dict
                d[k] = v
            else:
                # note: u[k] is a dict

                # get d[k], defaulting to a dict, if it doesn't previously
                # exist
                dv = d.setdefault(k, {})

                if not isinstance(dv, collections.abc.Mapping):
                    # d[k] is not a dict, so just set it to u[k],
                    # overriding whatever it was
                    d[k] = v
                else:
                    # both d[k] and u[k] are dicts, push them on the stack
                    # to merge
                    stack.append((dv, v))


def dicttoh5(
    treedict,
    h5file,
    h5path="/",
    mode="w",
    overwrite_data=False,
    create_dataset_args=None,
):
    """Write a nested dictionary to a HDF5 file, using keys as member names.

    If a dictionary value is a sub-dictionary, a group is created. If it is
    any other data type, it is cast into a numpy array and written as a
    :mod:`h5py` dataset. Dictionary keys must be strings and cannot contain
    the ``/`` character.

    taken from silx 0.10.1 
    (http://www.silx.org/doc/silx/0.10.1/_modules/silx/io/dictdump.html#dicttoh5)
    
    HERE EXTENDED TO SUPPORT 'NX_class' Attributes
    """
    # ... one could think about propagating something similar to the changes
    # made here back to silx
    import h5py
    from silx.io.dictdump import _SafeH5FileWrite, _prepare_hdf5_dataset
    import warnings

    if not h5path.endswith("/"):
        h5path += "/"

    with _SafeH5FileWrite(h5file, mode=mode) as h5f:
        for key in treedict:
            if isinstance(treedict[key], dict) and len(treedict[key]):
                # non-empty group: recurse
                dicttoh5(
                    treedict[key],
                    h5f,
                    h5path + key,
                    overwrite_data=overwrite_data,
                    create_dataset_args=create_dataset_args,
                )

                if "NX_class" not in h5f[h5path + key].attrs:
                    h5f[h5path + key].attrs["NX_class"] = "NXcollection"

            elif treedict[key] is None or (
                isinstance(treedict[key], dict) and not len(treedict[key])
            ):
                if (h5path + key) in h5f:
                    if overwrite_data is True:
                        del h5f[h5path + key]
                    else:
                        warnings.warn(
                            "key (%s) already exists. "
                            "Not overwriting." % (h5path + key)
                        )
                        continue
                # Create empty group
                h5f.create_group(h5path + key)
                # use NXcollection at first, might be overwritten an time later
                h5f[h5path + key].attrs["NX_class"] = "NXcollection"

            elif key == "NX_class":
                # assign NX_class
                try:
                    h5f[h5path].attrs["NX_class"] = treedict[key]
                except KeyError:
                    h5f.create_group(h5path)
                    h5f[h5path].attrs["NX_class"] = treedict[key]

            else:
                ds = _prepare_hdf5_dataset(treedict[key])
                # can't apply filters on scalars (datasets with shape == () )
                if ds.shape == () or create_dataset_args is None:
                    if h5path + key in h5f:
                        if overwrite_data is True:
                            del h5f[h5path + key]
                        else:
                            warnings.warn(
                                "key (%s) already exists. "
                                "Not overwriting." % (h5path + key)
                            )
                            continue

                    h5f.create_dataset(h5path + key, data=ds)

                else:
                    if h5path + key in h5f:
                        if overwrite_data is True:
                            del h5f[h5path + key]
                        else:
                            warnings.warn(
                                "key (%s) already exists. "
                                "Not overwriting." % (h5path + key)
                            )
                            continue

                    h5f.create_dataset(h5path + key, data=ds, **create_dataset_args)
