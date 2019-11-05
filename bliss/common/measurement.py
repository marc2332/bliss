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
from bliss.scanning.acquisition.calc import CalcAcquisitionDevice
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


class GroupedReadMixin:
    def __init__(self, controller):
        assert controller is not None
        self._controller_ref = weakref.ref(controller)

    @property
    def controller(self):
        return self._controller_ref()

    @property
    def name(self):
        return self.controller.name

    @property
    def fullname(self):
        try:
            return self.controller.fullname
        except AttributeError:
            return self.controller.name

    def prepare(self, *counters):
        pass

    def start(self, *counters):
        pass

    def stop(self, *counters):
        pass


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
    def __init__(
        self,
        name,
        grouped_read_handler=None,
        conversion_function=None,
        controller=None,
        unit=None,
    ):
        self._name = name
        self._controller = controller
        self.__read_handler = grouped_read_handler
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
    def read_handler(self):
        return self.__read_handler

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
    GROUPED_READ_HANDLERS = weakref.WeakKeyDictionary()

    class GroupedReadHandler(GroupedReadMixin):
        def _read(self, *counters, **kwargs):
            # execute '.read()', taking into account conversion function for each counter
            return [
                counters[i].conversion_function(x)
                for i, x in enumerate(self.read(*counters, **kwargs))
            ]

        def read(self, *counters, **kwargs):
            """
            this method should return a list of read values in the same order
            as counters
            """
            raise NotImplementedError

    def __init__(
        self,
        name,
        controller,
        grouped_read_handler=None,
        conversion_function=None,
        mode=SamplingMode.MEAN,
        unit=None,
    ):
        if grouped_read_handler:
            read_handler = grouped_read_handler
        else:
            if hasattr(controller, "read_all"):
                read_handler = CONTROLLER_GROUPED_READ_HANDLERS.setdefault(
                    controller, DefaultSamplingCounterGroupedReadHandler(controller)
                )
            else:
                read_handler = DefaultSingleSamplingCounterReadHandler(self)

        super().__init__(name, read_handler, conversion_function, controller, unit=unit)

        self.read = self.__read

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

    def __read(self):
        read_handler = self.read_handler
        if read_handler is None:
            raise NotImplementedError
        read_handler.prepare(self)
        read_handler.start(self)
        try:
            return read_handler._read(self)[0]
        finally:
            read_handler.stop(self)

    def read(self):
        raise NotImplementedError


class DefaultSamplingCounterGroupedReadHandler(SamplingCounter.GroupedReadHandler):
    def read(self, *counters, **kwargs):
        return self.controller.read_all(*counters)


class DefaultSingleSamplingCounterReadHandler(SamplingCounter.GroupedReadHandler):
    def __init__(self, controller):
        super().__init__(controller)
        # in this case, 'controller' is a SamplingCounter object,
        # its '.read()' method will be overwritten so we keep a
        # reference to the original one here to be able to call
        # it in the "group" .read() below
        self.__read = controller.read

    @property
    def fullname(self):
        # in case of a 'single' reader, the controller is
        # in fact the counter itself ; this reader object will
        # be used as 'device' by the AcquisitionDevice.
        # The fullname is used to build the acq. channels names,
        # we have to remove the last part since it will be
        # added when the channels will be instantiated from
        # counters, to avoid a repetition of the counter name,
        # like: "simulation_diode_controller:diode:diode"
        #                                          ^^^^^
        # Moreover, acq devices names are used to make the
        # db_name: it cannot be the "real" fullname
        # otherwise there would be again the same repetition
        name, _, _ = self.controller.fullname.partition(":")
        return name

    @property
    def name(self):
        # 'name' has to return the (truncated) fullname,
        # because it is used as name by the Acquisition Device,
        # and the name of each device in the chain is used
        # to build the db_name -- this is to avoid db_names
        # like: diode:diode
        #       ^^^^^^
        return self.fullname

    def prepare(self, *counters):
        return self.controller.controller.prepare()

    def start(self, *counters):
        return self.controller.controller.start()

    def stop(self, *counters):
        return self.controller.controller.stop()

    def read(self, *counters, **kwargs):
        return [self.__read(**kwargs)]


class SoftCounterController(SamplingCounterController):
    pass


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

    def read(self):
        return self.apply(self.get_value())


class IntegratingCounter(Counter):
    class GroupedReadHandler(GroupedReadMixin):
        def _get_values(self, from_index, *counters, **kwargs):
            # execute '.get_values()', taking into account conversion function for each counter
            return [
                counters[i].conversion_function(x)
                for i, x in enumerate(self.get_values(from_index, *counters, **kwargs))
            ]

        def get_values(self, from_index, *counters, **kwargs):
            """
            this method should return a list of numpy arrays in the same order
            as the counter_name
            """
            raise NotImplementedError

    def __init__(
        self,
        name,
        controller,
        grouped_read_handler=None,
        conversion_function=None,
        unit=None,
    ):
        if grouped_read_handler:
            read_handler = grouped_read_handler
        else:
            if hasattr(controller, "get_values"):
                read_handler = CONTROLLER_GROUPED_READ_HANDLERS.setdefault(
                    controller, DefaultIntegratingCounterGroupedReadHandler(controller)
                )
            else:
                read_handler = DefaultSingleIntegratingCounterReadHandler(self)

        super(IntegratingCounter, self).__init__(
            name,
            read_handler,
            conversion_function=conversion_function,
            controller=controller,
            unit=unit,
        )

        if self.get_values != IntegratingCounter.get_values:
            # method has been overwritten
            self.get_values = self.__get_values

    def __get_values(self, from_index, **kwargs):
        read_handler = self.read_handler
        if read_handler is None:
            raise NotImplementedError
        read_handler.prepare(self)
        read_handler.start(self)
        try:
            return read_handler._get_values(from_index, self, **kwargs)[0]
        finally:
            read_handler.stop(self)

    def get_values(self, from_index=0):
        """
        Overwrite in your class to provide an useful integrated counter class

        This method is called after the prepare and start on the master handler.
        This method can block until the data is ready or not and return empty data.
        When data is ready should return the data from the acquisition
        point **from_index**
        """
        raise NotImplementedError


class DefaultIntegratingCounterGroupedReadHandler(
    IntegratingCounter.GroupedReadHandler
):
    """
    Default read all handler for controller which have get_values method
    """

    def get_values(self, from_index, *counters, **kwargs):
        return self.controller.get_values(from_index, *counters)


class DefaultSingleIntegratingCounterReadHandler(IntegratingCounter.GroupedReadHandler):
    def __init__(self, controller):
        super().__init__(controller)
        self.__get_values = controller.get_values

    @property
    def fullname(self):
        # see DefaultSingleSamplingCounterReadHandler class
        # for details about .fullname and .name
        name, _, _ = self.controller.fullname.partition(":")
        return name

    @property
    def name(self):
        # see DefaultSingleSamplingCounterReadHandler class
        # for details about .fullname and .name
        return self.fullname

    def prepare(self, *counters):
        return self.controller.controller.prepare()

    def start(self, *counters):
        return self.controller.controller.start()

    def stop(self, *counters):
        return self.controller.controller.stop()

    def get_values(self, from_index, *counters, **kwargs):
        return [
            numpy.array(self.__get_values(from_index, **kwargs), dtype=numpy.double)
        ]


class CalcCounterChainNode(ChainNode):
    def get_acquisition_object(self, scan_params, acq_params):

        # --- Warn user if an unexpected is found in acq_params
        expected_keys = ["output_channels_list"]
        for key in acq_params.keys():
            if key not in expected_keys:
                print(
                    f"=== Warning: unexpected key '{key}' found in acquisition parameters for CalcAcquisitionDevice({self.controller}) ==="
                )

        output_channels_list = acq_params.get("output_channels_list")

        name = self.controller.calc_counter.name
        func = self.controller.calc_counter.calc_func

        acq_devices = []
        for node in self._calc_dep_nodes.values():
            acq_obj = node.acquisition_obj
            if acq_obj is None:
                raise ValueError(
                    f"cannot create CalcAcquisitionDevice: acquisition object of {node}({node.controller}) is None!"
                )
            else:
                acq_devices.append(acq_obj)

        return CalcAcquisitionDevice(name, acq_devices, func, output_channels_list)


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
