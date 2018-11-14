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

    from bliss.physics import units
    units.ur = ureg

"""

from functools import wraps
from inspect import getargspec

import pint

__all__ = ["ur", "units"]

#: unit registry
ur = pint.UnitRegistry()


def is_quantity(arg):
    """Return whether the given argument is a quantity."""
    return isinstance(arg, ur.Quantity)


def to_unit(arg):
    """Permissively cast the given argument into a unit."""
    return ur.Unit(arg) if arg else None


def values_to_units(dct):
    """Cast the values of the given dict into units"""
    return {k: to_unit(v) for k, v in list(dct.items())}


def convert_to(arg, unit):
    """Permissively convert the given argument into the given unit.

    The argument can either be a number or a quantity.
    """
    if not unit:
        return arg
    return arg.to(unit) if is_quantity(arg) else arg * unit


def units(**kwarg_units):
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
    result_unit = to_unit(kwarg_units.pop("result", None))
    kwarg_units = values_to_units(kwarg_units)

    def decorator(func):
        arg_spec = getargspec(func).args
        if not set(arg_spec).issuperset(kwarg_units):
            raise TypeError("units argument names differ from function argument names")

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Everything is a kwargs
            kwargs.update(list(zip(arg_spec, args)))
            # Check for quantity-free use case
            all_magnitude = all(
                not is_quantity(value)
                for key, value in list(kwargs.items())
                if key in kwarg_units
            )
            # Kwargs conversion
            kwargs = {
                key: convert_to(value, kwarg_units.get(key))
                for key, value in list(kwargs.items())
            }
            # Call the actual func
            result = func(**kwargs)
            if not result_unit:
                return result
            # Safety check
            if not is_quantity(result):
                raise TypeError("Function {!r} did not return a quantity".format(func))
            # Convert the result and return magnitude or quantity
            result = convert_to(result, result_unit)
            return result.magnitude if all_magnitude else result

        return wrapper

    return decorator
