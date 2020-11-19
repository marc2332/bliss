# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import builtins
import inspect
import gevent
from gevent import threadpool
import types
import itertools
import functools
import numpy
import collections.abc
import importlib.util
import distutils.util
from collections.abc import MutableMapping, MutableSequence
import socket
import fnmatch
import contextlib

from itertools import zip_longest
from bliss.common.event import saferef

import typeguard


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
    """
    Group elements of an iterable n by n.
    Return a zip object.
    s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ...
    Excedentary elements are discarded.
    Example:
    DEMO [5]: list(grouped([1,2,3,4,5], 2))
    Out  [5]: [(1, 2), (3, 4)]
    """
    return zip(*[iter(iterable)] * n)


def grouped_with_tail(iterable, n):
    """like grouped(), but do not remove last elements if they not reach the
    given length n"""
    iterator = iter(iterable)
    while True:
        partial = []
        for _ in range(n):
            try:
                value = next(iterator)
            except StopIteration:
                if len(partial):
                    yield partial
                return
            else:
                partial.append(value)
        yield partial


def flatten_gen(items):
    """Yield items from any nested iterable; see Reference."""
    for x in items:
        if isinstance(x, collections.abc.Iterable) and not isinstance(x, (str, bytes)):
            for sub_x in flatten(x):
                yield sub_x
        else:
            yield x


def flatten(items):
    """returns a list"""
    return [i for i in flatten_gen(items)]


def merge(items):
    """merge a list of list, first level only
    e.g.  merge([ [1,2], [3] ]) -> [1,2,3]
          merge([ [1,2], [[3,4]], [5] ]) -> [1,2,[3,4],5]
    """
    return [item for sublist in items for item in sublist]


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

    Return a method where _object_method_ attribute is filled with a dict of
    elements to characterize it.
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
        # Passe here if decorator is called with decorator arguments
        def object_method_wrap(func):
            return get_wrapper(func)

        return object_method_wrap
    else:
        # Passe here if the decorator is called without arguments
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
    for name, m in inspect.getmembers(src_obj.__class__, inspect.isfunction):
        # this loop carefully avoids to execute properties,
        # by looking for class members of type 'function' only.
        # Then, we get the supposed method with getattr;
        # if it is not a method we ignore the member
        member = getattr(src_obj, name)
        if not inspect.ismethod(member):
            continue

        if hasattr(member, "_object_attribute_"):
            attribute_info = dict(member._object_attribute_)
            filter_ = attribute_info.pop("filter", None)
            if filter_ is None or filter_(target_obj):
                add_object_attribute(target_obj, **member._object_attribute_)

        # For each method of <src_obj>: try to add it as a
        # custom method or as methods to set/get custom
        # attributes.
        try:
            method_info = dict(member._object_method_)
        except AttributeError:
            pass
        else:
            filter_ = method_info.pop("filter", None)
            if filter_ is None or filter_(target_obj):
                add_object_method(target_obj, member, pre_call, **method_info)


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
            if fget and "r" not in access_mode:
                access_mode = "rw"
            if fset and "w" not in access_mode:
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
        if isinstance(getattr(obj.__class__, member), property):
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


# the following code around `UserNamespace` is about a namespace that
# that has autocomplete_property properties itself.  It provides a
# signature completion in the bliss shell also for its members.
# More details in the doc bliss doc.
#
# BLISS [1]: from bliss.common.utils import UserNamespace
# BLISS [2]: def a(self,kwarg=13):
#       ...:     print(a)
# BLISS [4]: c=UserNamespace({"a":a})
# BLISS [5]: c.a(
#               a(self, kwarg=13)   # signature suggestion

# create a copy of module collections to have a copy of namedtuple
__SPEC = importlib.util.find_spec("collections")
mycollections = importlib.util.module_from_spec(__SPEC)
__SPEC.loader.exec_module(mycollections)
sys.modules["mycollections"] = mycollections

from mycollections import namedtuple as UserNamedtuple  # noqa E402

# patch property to trigger jedi signature hint
UserNamedtuple.__globals__["property"] = autocomplete_property


def UserNamespace(env_dict={}):
    klass = UserNamedtuple("namespace", env_dict, module=__name__ + ".namespace")

    def namespace_dir(self):
        __dir__ = super(self.__class__, self).__dir__()
        to_remove = []
        if "count" not in env_dict:
            to_remove.append("count")
        if "index" not in env_dict:
            to_remove.append("index")
        return [i for i in __dir__ if i not in to_remove]

    # patch dir function to hide "count" & "index" built-in tuples functions from jedi completion
    klass.__dir__ = namespace_dir
    ns = klass(**env_dict)
    return ns


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


def is_basictype(val):
    return isinstance(val, (int, str, float, type(None)))


def is_complextype(val):
    return isinstance(val, (MutableMapping, MutableSequence))


def is_mutsequence(val):
    return isinstance(val, MutableSequence)


def is_mutmapping(val):
    return isinstance(val, MutableMapping)


def is_sametype(val1, val2):
    if is_basictype(val1) and is_basictype(val2) and (type(val1) == type(val2)):
        return True
    elif is_mutmapping(val1) and is_mutmapping(val2):
        return True
    elif is_mutsequence(val1) and is_mutsequence(val2):
        return True


MISSING = "---missing---"


def prudent_update(d, u):
    """Updates a MutableMapping or MutalbeSequence 'd'
    from another one 'u'.
    The update is done trying to minimize changes: the
    update is done only on leaves of the tree if possible.
    This is to preserve the original object as much as possible.
    """
    if is_basictype(d) and is_basictype(u):
        if d != u:
            if d == MISSING:
                return u
            elif u == MISSING:
                return d
            return u
        else:
            return d  # prefer not to update
    elif is_complextype(d) and is_complextype(u):
        if is_sametype(d, u):
            # same type
            if is_mutmapping(d):
                for k, v in u.items():
                    if k in d:
                        d[k] = prudent_update(d[k], v)
                    else:
                        d[k] = v
            elif is_mutsequence(d):
                for num, (el1, el2) in enumerate(zip_longest(d, u, fillvalue=MISSING)):
                    if el2 == MISSING:
                        # Nothing to do
                        pass
                    else:
                        # missing el1 is managed by prudent_update
                        # when el1==MISSING el2!=MISSING -> el2 returned
                        value = prudent_update(el1, el2)
                        try:
                            d[num] = value
                        except IndexError:
                            d.append(value)
            else:
                raise NotImplementedError
            return d
        else:
            # not same type so the destination will be replaced
            return u
    elif is_basictype(d) and is_complextype(u):
        return u
    elif is_complextype(d) and is_basictype(u):
        return u
    else:
        raise NotImplementedError


def update_node_info(node, d):
    """updates the BaseHashSetting of a DataNode and does a deep update if needed. 
    parameters: node: DataNode or DataNodeContainer; d: dict"""
    assert type(d) == dict
    for key, value in d.items():
        tmp = node.info.get(key)
        if tmp and type(value) == dict and type(tmp) == dict:
            deep_update(tmp, value)
            node.info[key] = tmp
        else:
            node.info[key] = value


def rounder(template_number, number):
    """Round a number according to a template number
    
    assert rounder(0.0001, 16.12345) == "16.1234"
    assert rounder(1, 16.123) == "16"
    assert rounder(0.1, 8.5) == "8.5"
    """
    precision = (
        len(str(template_number).split(".")[-1])
        if not float(template_number).is_integer()
        else 0
    )
    return numpy.format_float_positional(
        number, precision=precision, unique=False, trim="-"
    )


def round(a, decimals=None, out=None, precision=None):
    """
    like numpy.round just with extened signature that 
    can deal with precision (a template number providing
    the smallest significant increment)

    assert round(16.123,precision=.2) == 16.1
    assert round(16.123,precision=1) == 16 
    assert round(16.123,precision=0.0001) == 16.123     
    """
    if decimals is not None:
        return numpy.round(a, decimals=decimals, out=out)
    elif precision is not None:
        digits = int(numpy.ceil(numpy.log10(1 / precision)))
        return numpy.round(a, digits)
    else:
        return numpy.round(a, decimals=0, out=out)


class ShellStr(str):
    """Subclasses str to give a nice representation in the Bliss shell"""

    def __info__(self):
        return str(self)


def get_open_ports(n):
    sockets = [socket.socket() for _ in range(n)]
    try:
        for s in sockets:
            s.bind(("", 0))
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:
            s.close()


class ColorTags:
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def __color_message(tag, msg):
    return "{0}{1}{2}".format(tag, msg, ColorTags.END)


def PURPLE(msg):
    return __color_message(ColorTags.PURPLE, msg)


def CYAN(msg):
    return __color_message(ColorTags.CYAN, msg)


def DARKCYAN(msg):
    return __color_message(ColorTags.DARKCYAN, msg)


def BLUE(msg):
    return __color_message(ColorTags.BLUE, msg)


def GREEN(msg):
    return __color_message(ColorTags.GREEN, msg)


def YELLOW(msg):
    return __color_message(ColorTags.YELLOW, msg)


def RED(msg):
    return __color_message(ColorTags.RED, msg)


def UNDERLINE(msg):
    return __color_message(ColorTags.UNDERLINE, msg)


def BOLD(msg):
    return __color_message(ColorTags.BOLD, msg)


def shorten_signature(original_function=None, *, annotations=None, hidden_kwargs=None):
    """decorator that can be used to simplyfy the signature displayed in the bliss shell.
       by default it is removing the annotation of each parameter or replacing it with a custum one.

       annotations: dict with parameters as key
       hidden_kwargs: list of parameters that should not be displayed but remain usable.
    """

    def _decorate(function):
        @functools.wraps(function)
        def wrapped_function(*args, **kwargs):
            return function(*args, **kwargs)

        sig = inspect.signature(function)
        params = list(sig.parameters.values())
        to_be_removed = list()
        for i, param in enumerate(params):
            if hidden_kwargs and param.name in hidden_kwargs:
                to_be_removed.append(param)
            elif annotations and param.name in annotations.keys():
                params[i] = param.replace(annotation=annotations[param.name])
                # ,default=inspect.Parameter.empty)
            else:
                params[i] = param.replace(annotation=inspect.Parameter.empty)
        for p in to_be_removed:
            params.remove(p)
        sig = sig.replace(parameters=params)
        wrapped_function.__signature__ = sig

        return wrapped_function

    if original_function:
        return _decorate(original_function)

    return _decorate


def custom_error_msg(
    exception_type, message, new_exception_type=None, display_original_msg=False
):
    """decorator to modify exception and/or the corresponding message"""

    def _decorate(function):
        @functools.wraps(function)
        def wrapped_function(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception as e:
                if isinstance(e, exception_type):
                    if new_exception_type:
                        new_exception = new_exception_type
                    else:
                        new_exception = exception_type
                    if display_original_msg:
                        raise new_exception(message + " " + str(e)) from e
                    else:
                        raise new_exception(message) from e
                else:
                    raise

        return wrapped_function

    return _decorate


class TypeguardTypeError(TypeError):
    """TypeError that is used only in Typeguard module
       should be pushed to typeguard repositoy
    """

    pass


typeguard.TypeError = TypeguardTypeError


def typeguardTypeError_to_hint(function):
    """decorator that transforms TypeError into a simpliyed RuntimeError
    Intended use: Modifying the message when using @typeguard.typechecked
    """

    @functools.wraps(function)
    def wrapped_function(*args, **kwargs):
        sig = inspect.signature(function)
        params = list(sig.parameters.values())
        msg = (
            "Intended Usage: "
            + function.__name__
            + "("
            + ", ".join(
                [p.name for p in params if p.default == inspect.Parameter.empty]
            )
            + ")  Hint:"
            + ""
        )
        return custom_error_msg(
            TypeguardTypeError,
            msg,
            new_exception_type=RuntimeError,
            display_original_msg=True,
        )(function)(*args, **kwargs)

    return wrapped_function


def typecheck_var_args_pattern(args_pattern, empty_var_pos_args_allowed=False):
    """decorator that can be used for typechecking of *args that have to follow a certain pattern e.g. 
    @typecheck_var_args_pattern([_scannable,_float])
    def umv(*args):
     ...
    """

    def decorate(function):
        @functools.wraps(function)
        def wrapped_function(*args, **kwargs):
            sig = inspect.signature(function)
            params = list(sig.parameters.values())
            for i, param in enumerate(params):
                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    var_args = args[i:]
                    if not empty_var_pos_args_allowed and len(var_args) == 0:
                        raise TypeguardTypeError(
                            f"Arguments of type {args_pattern} missing!"
                        )
                    if len(var_args) % len(args_pattern) != 0:
                        raise TypeguardTypeError(
                            f"Wrong number of arguments (not a multiple of {len(args_pattern)} [{args_pattern}])"
                        )
                    for j, a in enumerate(var_args):
                        typeguard.check_type(
                            f"{param.name}[{j}]", a, args_pattern[j % len(args_pattern)]
                        )
            return function(*args, **kwargs)

        return wrapped_function

    return decorate


def modify_annotations(annotations):
    """Modify the annotation in an existing signature
    @modify_annotations({"args": "motor1, rel. pos1, motor2, rel. pos2, ..."})
    def umvr(*args):
        ...
    """

    def decorate(function):
        def wrapped_function(*args, **kwargs):
            return function(*args, **kwargs)

        functools.update_wrapper(wrapped_function, function)
        sig = inspect.signature(function)
        params = list(sig.parameters.values())
        for i, param in enumerate(params):
            if param.name in annotations:
                params[i] = param.replace(annotation=annotations[param.name])
        sig = sig.replace(parameters=params)
        wrapped_function.__signature__ = sig
        return wrapped_function

    return decorate


def is_pattern(pattern: str) -> bool:
    """Return true if the input string is a pattern for `get_matching_names`.
    """
    if "?" in pattern:
        return True
    if "*" in pattern:
        return True
    if "[" in pattern:
        return True
    return False


def get_matching_names(patterns, names, strict_pattern_as_short_name=False):

    """ search a pattern into a list of names (unix pattern style) 

        pattern     |       meaning
        ------------|-------------------------------------------
          *         | matches everything
          ?         | matches any single character
          [seq]     | matches any character in seq
          [!seq]    | matches any character not in seq

        arguments:
          - patterns: a list of patterns
          - names: a list of names
          - strict_pattern_as_short_name: if True patterns without special character,
            are transformed like this: 'pattern' -> '*:pattern' (as the 'short name' part of a 'fullname')

        return: dict { pattern : matching names }

    """

    special_char = ["*", ":"]

    if not isinstance(patterns, (list, tuple)):
        patterns = [patterns]

    matches = {}
    for pat in patterns:

        if not isinstance(pat, str):
            pat = str(pat)

        sub_pat = [pat]

        if strict_pattern_as_short_name:
            if all([sc not in pat for sc in special_char]):
                sub_pat = [f"*:{pat}", f"*:{pat}:*", f"{pat}:*"]

        # store the fullname of matching counters
        matching_names = []
        for _pat in sub_pat:

            for name in names:
                if fnmatch.fnmatch(name, _pat):
                    matching_names.append(name)

            if matching_names:
                break

        matches[pat] = matching_names

    return matches


def _tp_print(tp, print_func, *args, **kwargs):
    return tp.spawn(print_func, *args, **kwargs).get()


@contextlib.contextmanager
def nonblocking_print(
    data={"count": 0, "orig_print": None, "pool": threadpool.ThreadPool(1)}
):
    if data["count"] == 0:
        orig_print = builtins.print
        data["orig_print"] = orig_print
        builtins.print = functools.partial(_tp_print, data["pool"], orig_print)
    data["count"] += 1
    try:
        yield
    finally:
        data["count"] -= 1
        if data["count"] == 0:
            builtins.print = data["orig_print"]


def auto_coerce(s):
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

    def boolify(s, **keys):
        if s in ("True", "true"):
            return True
        if s in ("False", "false"):
            return False
        raise ValueError("Not Boolean Value!")

    # Cast to standard types
    for caster in (boolify, int, float):
        try:
            return caster(s)
        except (ValueError, TypeError):
            pass
    return s


class Singleton(type):
    def __init__(cls, name, bases, d):
        super(Singleton, cls).__init__(name, bases, d)
        cls.instance = None

    def __call__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kwargs)
        return cls.instance
