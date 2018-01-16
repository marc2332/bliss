# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Physical units for engineering and science

Implementation based on :mod:`pint`.

Usage::

    >>> from bliss.physics.units import ur

    >>> # use ur as a pint UnitRegistry
    >>> mass = 0.1*ur.mg
    >>> E = mass * ur.c**2
    >>> print( E.to(ur.kJ) )
    8987551.78737 kilojoule

    >>> # decorate your methods to ensure proper units
    >>> @ur.units(mass='kg', result='J')
    ... def energy(mass):
    ...     return mass * ur.c**2

    >>> # passing a Quantity will give you back a Quantity
    >>> print( energy(mass) )
    8987551787.37 joule

    >>> # passing a float will assume it is in the proper (kg)
    >>> # and will give you back a float in the corresponding unit (J)
    >>> print( energy(0.1e-6) )
    8987551787.37


Advanced usage
--------------

Use another UnitRegistry
~~~~~~~~~~~~~~~~~~~~~~~~

Bliss unit system creates a default UnitRegistry (ur).

If you want to interact with another library which also uses pint it is
important that both libraries use the same UnitRegistry.

This library allows you to change the active UnitRegistry. You should do
this as soon as possible in the code of your application::

    import pint
    ureg = UnitRegistry()

    from bliss.physics import ur
    ur.registry = ureg

"""

from functools import wraps
from inspect import getargspec

import pint

_UnitNull = lambda value: value

_to_arg_type = lambda a: _UnitNull(a) if a is None else ur.Unit(a)

def _to_arg_types(kwarg_types):
    return {k:_to_arg_type(a) for k, a in kwarg_types.items()}

def _to_arg(arg, arg_type):
    if arg is None:
        return None, True
    is_unit = isinstance(arg_type, ur.Unit)
    is_quantity = isinstance(arg, ur.Quantity)
    if is_unit:
        arg = arg.to(arg_type) if is_quantity else arg*arg_type
    return arg, is_quantity and is_unit

def _create_args_converter(kwarg_types):
    kwarg_types = _to_arg_types(kwarg_types)
    def convert(kwargs):
        any_quantity_arg = False
        result = {}
        for arg_name, arg in kwargs.iteritems():
            arg_type = kwarg_types.get(arg_name)
            arg, is_quantity = _to_arg(arg, arg_type)
            any_quantity_arg |= is_quantity
            result[arg_name] = arg
        return result, any_quantity_arg
    return convert

def _create_result_converter(result_type):
    result_type = _to_arg_type(result_type)
    is_unit = isinstance(result_type, ur.Unit)
    if is_unit:
        def convert(result, no_quantity):
            if isinstance(result, ur.Quantity):
                result = result.to(result_type)
                if no_quantity:
                    result = result.magnitude
                return result
            raise TypeError('Method does not return a quantity')

    else:
        def convert(result, no_quantity):
            return result
    return convert


def units(**kwarg_types):
    """
    Use as a decorator to protect your function against unit errors.

    Each keyword argument must be an argument of the function. The
    value is the unit (string or Unit) in which your function argument
    should be called with.

    An extra argument *result* should provide the Unit for the expected
    return value. And yes, you cannot have a function which has an
    argument called *result* but that is just good naming!

    Missing arguments will be ignored.

    Example::

        from bliss.physics.units import ur, units

        @units(mass='kg', result=ur.J)
        def energy(mass):
            return mass * ur.c**2

    When you call a decorated function, it will return a Quantity if the
    *result* is a Unit and at least one of the arguments is a Quantity. If none
    of the arguments is a Quantity the result is a float with a value in the
    units specified by *result*
    """
    result_type = kwarg_types.pop('result', None)
    convert_args = _create_args_converter(kwarg_types)
    convert_result = _create_result_converter(result_type)

    def decorator(func):
        arg_spec = getargspec(func).args
#        if set(arg_spec) != kwarg_names:
        if not set(arg_spec).issuperset(kwarg_types):
            raise TypeError('units argument names differ from ' \
                            'function argument names')
        @wraps(func)
        def wrapper(*args, **kwargs):
            kwargs.update(zip(arg_spec, args))
            kwargs, any_quantity_arg = convert_args(kwargs)
            result = func(**kwargs)
            result = convert_result(result, not any_quantity_arg)
            return result
        return wrapper
    return decorator


class Units(object):
    """Wrapper around the pint.UnitRegistry to make the API
    a little bit more friendly. Don't use this directly on your code"""

    def __init__(self):
        self.__dict__['__unit_registry'] = None

    @property
    def registry(self):
        ur = self.__dict__['__unit_registry']
        if ur is None:
            import pint
            self.__dict__['__unit_registry'] = ur = pint.UnitRegistry()
        return ur

    def __dir__(self):
        return dir(self.registry) + ['registry', 'units']

    @registry.setter
    def registry(self, reg):
        self.__unit_registry = reg

    def units(self, **kwargs):
        return units(**kwargs)

    def __getattr__(self, name):
        return getattr(self.registry, name)

    def __setattr__(self, key, value):
        setattr(self.registry, key, value)

    def __call__(self, *args, **kwargs):
        return self.registry(*args, **kwargs)

    def __getitem__(self, key):
        return self.registry[key]

    def __setitem__(self, key, value):
        self.registry[key] = value

#: unit registry
ur = Units()
