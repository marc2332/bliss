# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import inspect
import types
import itertools
import functools

class WrappedMethod(object):
  def __init__(self, control, method_name):
    self.method_name = method_name
    self.control = control

  def __call__(self, this, *args, **kwargs):
    return getattr(self.control, self.method_name)(*args, **kwargs)

def wrap_methods(from_object, target_object):
   for name in dir(from_object):
       if inspect.ismethod(getattr(from_object, name)):
         if hasattr(target_object, name) and inspect.ismethod(getattr(target_object, name)):
           continue
         setattr(target_object, name, types.MethodType(WrappedMethod(from_object, name), target_object, target_object.__class__))

def add_property(inst, name, method):
  cls = type(inst)
  if not hasattr(cls, '__perinstance'):
    cls = type(cls.__name__, (cls,), {})
    cls.__perinstance = True
    inst.__class__ = cls
  setattr(cls, name, property(method))


def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return itertools.izip(*[iter(iterable)]*n)


"""
functions to add custom attributes and commands to an object.
"""
def add_object_method(obj, method, pre_call, name=None, args=[], types_info=(None, None)):

    if name is None:
        name = method.im_func.func_name

    def call(self, *args, **kwargs):
        if callable(pre_call):
            pre_call(self, *args, **kwargs)

        return method.im_func(method.im_self, *args, **kwargs)

    obj._add_custom_method(
        types.MethodType(functools.partial(call, *([obj] + args)),
                         obj), name, types_info)


def object_method(method=None, name=None, args=[], types_info=(None, None)):
    """
    Decorator to add a custom method to an object.

    The same as add_object_method but its purpose is to be used as a
    decorator to the controller method which is to be exported as object method.
    """
    if method is None:
        # Passes here if decorator parameters are not present ???.
        # ...
        return functools.partial(object_method, name=name, args=args,
                                 types_info=types_info)

    # Returns a method where _object_method_ attribute is filled with a
    # dict of elements to characterize it.
    method._object_method_ = dict(name=name, args=args, types_info=types_info)

    return method


def add_object_attribute(obj, name=None, fget=None, fset=None, args=[], type_info=None):

    cust_attr_dict = getattr(obj, "_%s__custom_attributes_dict" % obj.__class__.__name__)

    if cust_attr_dict.get(name):
        access_mode = cust_attr_dict[name][1]
        if fget and not 'r' in access_mode:
            access_mode = "rw"

        if fset and not 'w' in access_mode:
            access_mode = "rw"

        cust_attr_dict[name] = (type_info, access_mode)
    else:
        if fget:
            cust_attr_dict[name] = (type_info, "r")
        elif fset:
            cust_attr_dict[name] = (type_info, "w")
        else:
            raise RuntimeError("impossible case: must have fget or fset...")


"""
decorators for set/get methods to access to custom attributes
"""
def object_attribute_get(get_method=None, name=None, args=[], type_info=None):
    if get_method is None:
        return functools.partial(object_attribute_get, name=name, args=args,
                                 type_info=type_info)

    if name is None:
        name = get_method.func_name
    attr_name = name
    if attr_name.startswith("get_"):
        attr_name = attr_name[4:] # removes leading "get_"

    get_method._object_method_ = dict(name=name, args=args, types_info=("None", type_info))

    if not hasattr(get_method, "_object_attribute_"):
        get_method._object_attribute_ = dict()
    get_method._object_attribute_.update(name=attr_name, fget=get_method, args=args, type_info=type_info)

    return get_method

def object_attribute_set(set_method=None, name=None, args=[], type_info=None):
    if set_method is None:
        return functools.partial(object_attribute_set, name=name, args=args,
                                 type_info=type_info)

    if name is None:
        name = set_method.func_name
    attr_name = name
    if attr_name.startswith("set_"):
        attr_name = attr_name[4:] # removes leading "set_"

    set_method._object_method_ = dict(name=name, args=args, types_info=(type_info, "None"))

    if not hasattr(set_method, "_object_attribute_"):
        set_method._object_attribute_ = dict()
    set_method._object_attribute_.update(name=attr_name, fset=set_method, args=args, type_info=type_info)

    return set_method


def set_custom_members(src_obj, target_obj, pre_call=None):
    # Creates custom methods and attributes for <target_obj> object
    # using <src_object> object definitions.
    # Populates __custom_methods_list and __custom_attributes_dict
    # for tango device server.
    for name, member in inspect.getmembers(src_obj):
        # Just fills the list.
        if hasattr(member, "_object_attribute_"):
            add_object_attribute(target_obj,  **member._object_attribute_)

        # For each method of <src_obj>: try to add it as a
        # custom method or as methods to set/get custom
        # attributes.
        try:
            add_object_method(target_obj, member, pre_call, **member._object_method_)
        except AttributeError:
            pass

