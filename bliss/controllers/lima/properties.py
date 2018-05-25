# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools
import enum
import inspect
import re

from bliss.common.tango import DevFailed

LimaProperty = type('LimaProperty', (property, ), {})

def camel_to_snake(camelCasedStr):
    """ 
    This function converts to snake_case from camelCase
    """
    first_cap_re = re.compile(r'(.)([A-Z][a-z]+)')
    all_cap_re = re.compile('([a-z0-9])([A-Z])')
    sub1            = first_cap_re.sub(r'\1_\2', camelCasedStr)
    snake_cased_str = all_cap_re.sub(r'\1_\2', sub1).lower()
    return snake_cased_str.replace('__', '_')

class LimaAttrGetterSetter(object):
    def __init__(self, proxy):
        self.__proxy = proxy

    def _get_enum(self, values_enum):
        return values_enum

    def _r_attr_func(self, attr, values_enum=None):
        v = self.__proxy.read_attribute(attr).value
        if values_enum:
            return values_enum[v]
        else:
            return v

    def _w_attr_func(self, value, attr, values_enum=None):
        if values_enum:
            if value in values_enum:
                v = value.name
            else:
                try:
                    v = values_enum[value].name
                except KeyError:
                    raise ValueError("'%s` only accepts following values: %s" % (attr,
                                     ", ".join([x.name for x in \
                                               list(values_enum)])))
        else:
            v = value
        return self.__proxy.write_attribute(attr, v)

    def __dir__(self):
        properties = dict(inspect.getmembers(self.__class__,
                                             lambda x: isinstance(x, property)))
        return sorted(properties.keys())

    def __repr__(self):
        # only show Lima properties, ie. properties that are added
        # by the class generated by the LimaProperties function
        properties = inspect.getmembers(self.__class__,
                                        lambda x: isinstance(x, LimaProperty))
        display_list = []
        for pname, p in properties:
            try:
                display_list.append("%s = %s" % (pname, p.fget(self)))
            except DevFailed:
                display_list.append("%s = ? (failed to read attribute)" % pname)
        return "\n".join(display_list)

    
def LimaProperties(name, proxy, prefix=None, strip_prefix=False,
                   base_class=None, base_class_args=None):
    base_classes = [] if base_class is None else [base_class]
    base_classes.append(LimaAttrGetterSetter)
    klass = type(name, tuple(base_classes), {})
    attr_cfg_list = proxy.attribute_list_query()
    for attr_info in attr_cfg_list:
        attr = attr_info.name
        if prefix is None or attr.startswith(prefix):
            attr_username = camel_to_snake(attr if not strip_prefix or prefix is None else \
                            re.sub(prefix, '', attr))
            if attr_username in dir(klass):
                # do not overwrite existing property/member
                continue
            values_enum = None
            if attr_info.data_format == 0 and attr_info.data_type == 8:
                # SCALAR, DevString
                possible_values = proxy.getAttrStringValueList(attr)
                if possible_values:
                    values_enum = enum.Enum(attr_username+"_enum", { v: v for v in possible_values})
            r_attr_func = functools.partial(klass._r_attr_func, attr=attr,
                                            values_enum=values_enum)
            if attr_info.writable == 0:
                # READ only
                w_attr_func = None
            else:
                w_attr_func = functools.partial(klass._w_attr_func,
                                                attr=attr,
                                                values_enum=values_enum)
            setattr(klass, attr_username, LimaProperty(r_attr_func, w_attr_func))
            if values_enum is not None:
                setattr(klass, attr_username+"_enum",
                        property(functools.partial(klass._get_enum,
                                                   values_enum=values_enum)))
    if base_class:
        if base_class_args:
            o = klass(*base_class_args)
        else:
            o = klass()
        LimaAttrGetterSetter.__init__(o, proxy)
        return o
    else:
        return klass(proxy)
