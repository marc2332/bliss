# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# run tests for this module from the bliss root directory with:
# python -m unittest discover -s tests/acquisition -v

import numpy
import inspect
import weakref

from collections import namedtuple
from bliss.common.utils import autocomplete_property
from bliss.controllers.acquisition import CounterController, counter_namespace
from bliss.scanning.chain import ChainNode
from bliss.scanning.acquisition.counter import SamplingCounterController, SamplingMode
from bliss.scanning.acquisition.calc import CalcAcquisitionSlave
from bliss import global_map


CONTROLLER_GROUPED_READ_HANDLERS = weakref.WeakKeyDictionary()


def add_conversion_function(obj, method_name, function):
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


# Base counter class


class BaseCounter:
    """Define a standard counter interface."""

    # Properties

    @autocomplete_property
    def controller(self):
        """A controller or None."""
        return None

    @property
    def name(self):
        """A unique name within the controller scope."""
        raise NotImplementedError

    @property
    def dtype(self):
        """The data type as used by numpy."""
        return numpy.float

    @property
    def shape(self):
        """The data shape as used by numpy."""
        return ()

    def get_metadata(self):
        return {}

    # Extra logic

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


class Counter(BaseCounter):
    def __init__(self, name, conversion_function=None, controller=None, unit=None):
        self._name = name
        self._controller = controller
        self._conversion_function = (
            conversion_function if conversion_function is not None else lambda x: x
        )
        assert callable(self._conversion_function)
        self._unit = unit
        parents_list = ["counters"] + ([controller] if controller is not None else [])
        global_map.register(self, parents_list, tag=self.name)

    # Standard interface

    @autocomplete_property
    def controller(self):
        return self._controller

    @property
    def name(self):
        return self._name

    @property
    def unit(self):
        return self._unit

    # Extra interface

    @property
    def conversion_function(self):
        return self._conversion_function


class SamplingCounter(Counter):
    def __init__(
        self,
        name,
        controller,
        conversion_function=None,
        mode=SamplingMode.MEAN,
        unit=None,
    ):
        super().__init__(name, conversion_function, controller, unit=unit)

        # self.read = self.__read

        if isinstance(mode, SamplingMode):
            self._mode = mode
        else:
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

    def read(self):
        self.controller.prepare(self)
        self.controller.start(self)
        try:
            value = self.controller.read_all(self)[0]
            return self.conversion_function(value)
        finally:
            self.controller.stop(self)


class SoftCounterController(SamplingCounterController):
    def read(self, counter):
        return counter.apply(counter.get_value())


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

        from bliss.common.measurement import SoftCounter

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
        self.__name = name

        super().__init__(name, SoftCounterController(ctrl_name), mode=mode, unit=unit)

    @property
    def name(self):
        return self.__name

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


class IntegratingCounter(Counter):
    def __init__(self, name, controller, conversion_function=None, unit=None):

        super().__init__(
            name,
            conversion_function=conversion_function,
            controller=controller,
            unit=unit,
        )

    def get_values(self, from_index=0):
        """
        Overwrite in your class to provide an useful integrated counter class

        This method is called after the prepare and start on the master handler.
        This method can block until the data is ready or not and return empty data.
        When data is ready should return the data from the acquisition
        point **from_index**
        """
        self.controller.prepare(self)
        self.controller.start(self)
        try:
            value = self.controller.get_values(from_index, self)[0]
            return self.conversion_function(value)
        finally:
            self.controller.stop(self)


class CalcCounterChainNode(ChainNode):
    def get_acquisition_object(self, scan_params, acq_params):

        # --- Warn user if an unexpected is found in acq_params
        expected_keys = ["output_channels_list"]
        for key in acq_params.keys():
            if key not in expected_keys:
                print(
                    f"=== Warning: unexpected key '{key}' found in acquisition parameters for CalcAcquisitionSlave({self.controller}) ==="
                )

        output_channels_list = acq_params.get("output_channels_list")

        name = self.controller.calc_counter.name
        func = self.controller.calc_counter.calc_func

        acq_devices = []
        for node in self._calc_dep_nodes.values():
            acq_obj = node.acquisition_obj
            if acq_obj is None:
                raise ValueError(
                    f"cannot create CalcAcquisitionSlave: acquisition object of {node}({node.controller}) is None!"
                )
            else:
                acq_devices.append(acq_obj)

        return CalcAcquisitionSlave(name, acq_devices, func, output_channels_list)


class CalcCounter(BaseCounter):
    def __init__(self, name, controller, calc_function):
        self.__name = name
        self.__controller = controller
        self.__calc_function = calc_function

    @property
    def name(self):
        return self.__name

    @property
    def calc_func(self):
        return self.__calc_function

    @property
    def fullname(self):
        return self.name

    @autocomplete_property
    def controller(self):
        return self.__controller


class CalcCounterController(CounterController):
    def __init__(self, name, calc_function, *dependent_counters):
        super().__init__("calc_counter", chain_node_class=CalcCounterChainNode)
        self.__dependent_counters = dependent_counters
        self.__counter = CalcCounter(name, self, calc_function)
        global_map.register(self.__counter, ["counters"], tag=name)

    @property
    def calc_counter(self):
        return self.__counter

    @property
    def counters(self):
        self._counters = {self.__counter.name: self.__counter}

        for cnt in self.__dependent_counters:
            if isinstance(cnt, CalcCounter):
                self._counters.update(
                    {cnt.name: cnt for cnt in cnt.controller.counters}
                )
            else:
                self._counters[cnt.name] = cnt
        return counter_namespace(self._counters)
