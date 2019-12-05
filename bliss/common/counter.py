# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# run tests for this module from the bliss root directory with:
# python -m unittest discover -s tests/acquisition -v

from collections import namedtuple

import enum
import inspect
import numpy

from bliss import global_map
from bliss.common.utils import autocomplete_property


def add_conversion_function(obj, method_name, function):
    """ add a conversion method to an object """
    meth = getattr(obj, method_name)
    if inspect.ismethod(meth):
        if callable(function):

            def new_method(*args, **kwargs):
                values = meth(*args, **kwargs)
                return function(values)

            setattr(obj, method_name, new_method)
        else:
            raise ValueError("conversion function must be callable")
    else:
        raise ValueError("'%s` is not a method" % method_name)


@enum.unique
class SamplingMode(enum.IntEnum):
    """SamplingCounter modes:
    * MEAN: emit the mathematical average
    * STATS: in addition to MEAN, use iterative algorithms to emit std,min,max,N etc.
    * SAMPLES: in addition to MEAN, emit also individual samples as 1D array
    * SINGLE: emit the first value (if possible: call read only once)
    * LAST: emit the last value 
    * INTEGRATE: emit MEAN multiplied by counting time
    """

    MEAN = enum.auto()
    STATS = enum.auto()
    SAMPLES = enum.auto()
    SINGLE = enum.auto()
    LAST = enum.auto()
    INTEGRATE = enum.auto()
    INTEGRATE_STATS = enum.auto()


class Counter:
    """ Counter class """

    def __init__(self, name, controller, conversion_function=None, unit=None):
        self._name = name
        self._controller = controller
        self._conversion_function = (
            conversion_function if conversion_function is not None else lambda x: x
        )
        assert callable(self._conversion_function)
        self._unit = unit
        parents_list = ["counters"] + ([controller] if controller is not None else [])
        global_map.register(self, parents_list, tag=self.name)

    @property
    def name(self):
        return self._name

    @autocomplete_property
    def controller(self):
        return self._controller

    @property
    def dtype(self):
        """The data type as used by numpy."""
        return numpy.float

    @property
    def shape(self):
        """The data shape as used by numpy."""
        return ()

    @property
    def fullname(self):
        """A unique name within the session scope.

        The standard implementation defines it as:
        `[<master_controller_name>].[<controller_name>].<counter_name>`
        """
        args = []
        if self.controller.master_controller is not None:
            args.append(self.controller.master_controller.name)
        args.append(self.controller.name)
        args.append(self.name)
        return ":".join(args)

    @property
    def unit(self):
        return self._unit

    @property
    def conversion_function(self):
        return self._conversion_function

    def get_metadata(self):
        return {}


class SamplingCounter(Counter):
    def __init__(
        self,
        name,
        controller,
        conversion_function=None,
        mode=SamplingMode.MEAN,
        unit=None,
    ):
        super().__init__(
            name, controller, conversion_function=conversion_function, unit=unit
        )

        if isinstance(mode, SamplingMode):
            self._mode = mode
        else:
            # <mode> can also be a string
            self._mode = SamplingMode[mode]

        stats = namedtuple(
            "SamplingCounterStatistics",
            "mean N std var min max p2v count_time timestamp",
        )
        self._statistics = stats(
            numpy.nan,
            numpy.nan,
            numpy.nan,
            numpy.nan,
            numpy.nan,
            numpy.nan,
            numpy.nan,
            None,
            None,
        )

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        try:
            if value in list(SamplingMode):
                self._mode = SamplingMode(value)
            else:
                self._mode = SamplingMode[value]
        except KeyError:
            raise ValueError(
                "Invalid mode '%s', the mode must be in %s"
                % (value, list(SamplingMode.__members__.keys()))
            )

    @autocomplete_property
    def statistics(self):
        return self._statistics


class IntegratingCounter(Counter):
    def __init__(self, name, controller, conversion_function=None, unit=None):

        super().__init__(
            name, controller, conversion_function=conversion_function, unit=unit
        )


class SoftCounter(SamplingCounter):
    """
    Transforms any given python object into a sampling counter.
    By default it assumes the object has a member called *value* which will be
    used on a read.
    You can overwrite this behaviour by passing the name of the object member
    as value. It can be an object method, a property/descriptor or even a simple
    attribute of the given object.

    If no name is given, the counter name is the string representation of the
    value argument.
    The counter full name is `controller.name` + '.' + counter_name. If no
    controller is given, the obj.name is used instead of controller.name. If no
    obj is given the counter full name is counter name.

    You can pass an optional apply function if you need to transform original
    value given by the object into something else.

    Here are some examples::

        from bliss.common.counter import SoftCounter

        class Potentiostat:

            def __init__(self, name):
                self.name = name

            @property
            def potential(self):
                return float(self.comm.write_readline('POT?\n'))

            def get_voltage(self):
                return float(self.comm.write_readline('VOL?\n'))

        pot = Potentiostat('p1')

        # counter from an object property (its name is 'potential'.
        # Its full name is 'p1.potential')
        pot_counter = SoftCounter(pot, 'potential')

        # counter form an object method
        milivol_counter = SoftCounter(pot, 'get_voltage', name='voltage',
                                      apply=lambda v: v*1000)

        # you can use the counters in any scan
        from bliss.common.standard import loopscan
        loopscan(10, 0.1, pot_counter, milivol_counter)
    """

    def __init__(
        self,
        obj=None,
        value="value",
        name=None,
        apply=None,
        mode=SamplingMode.MEAN,
        unit=None,
        conversion_function=None,
    ):
        if obj is None and inspect.ismethod(value):
            obj = value.__self__
        self.get_value, value_name = self.get_read_func(obj, value)
        name = value_name if name is None else name
        obj_has_name = hasattr(obj, "name") and isinstance(obj.name, str)
        if obj_has_name:
            ctrl_name = obj.name
        elif obj is None:
            ctrl_name = name
        else:
            ctrl_name = type(obj).__name__
        if apply is None:
            apply = lambda x: x
        self.apply = apply

        from bliss.controllers.counter import SoftCounterController

        super().__init__(
            name,
            SoftCounterController(ctrl_name),
            mode=mode,
            unit=unit,
            conversion_function=conversion_function,
        )

    @staticmethod
    def get_read_func(obj, value):
        if callable(value):
            value_name = value.__name__
            value_func = value
        else:
            otype = type(obj)
            value_name = value
            val = getattr(otype, value_name, None)
            if val is None or not callable(val):

                def value_func():
                    return getattr(obj, value_name)

            else:

                def value_func():
                    return val(obj)

            value_func.__name__ = value_name
        return value_func, value_name


class CalcCounter(Counter):
    pass
