# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# run tests for this module from the bliss root directory with:
# python -m unittest discover -s tests/acquisition -v

import numpy
import weakref
from collections import namedtuple

from bliss.common.utils import add_conversion_function


# Counter namespaces

def flat_namespace(dct):
    """A namespace allowing names with dots."""
    mapping = dict(dct)

    class getter(object):
        def __init__(self, parent, prefix):
            self.parent = parent
            self.prefix = prefix

        def __getattr__(self, key):
            return getattr(self.parent, self.prefix + key)

    class namespace(tuple):

        __slots__ = ()
        _fields = sorted(mapping)
        __dict__ = property(lambda _: mapping)

        def __getattr__(self, arg):
            if arg in mapping:
                return mapping[arg]
            if arg.startswith('__'):
                raise AttributeError(arg)
            for field in self._fields:
                if field.startswith(arg + '.'):
                    return getter(self, arg + '.')
            raise AttributeError(arg)

        def __setattr__(self, arg, value):
            raise AttributeError("can't set attribute")

        def __repr__(self):
            reprs = (
                '{}={!r}'.format(field, mapping[field])
                for field in self._fields)
            return '{}({})'.format('namespace', ', '.join(reprs))

    return namespace(mapping[field] for field in namespace._fields)


def namespace(dct):
    if any('.' in key for key in dct):
        return flat_namespace(dct)
    return namedtuple('namespace', sorted(dct))(**dct)


def counter_namespace(counters):
    return namespace({counter.name: counter for counter in counters})


# Base counter class

class GroupedReadMixin(object):
    def __init__(self, controller):
        self._controller_ref = weakref.ref(controller)

    @property
    def name(self):
        return self.controller.name

    @property
    def controller(self):
        return self._controller_ref()

    @property
    def id(self):
        return id(self.controller)

    def prepare(self, *counters):
        pass

    def start(self, *counters):
        pass

    def stop(self, *counters):
        pass


class BaseCounter(object):
    """Define a standard counter interface."""

    # Properties

    @property
    def controller(self):
        """A controller or None."""
        return None

    @property
    def master_controller(self):
        """A master controller or None."""
        return None

    @property
    def name(self):
        """A unique name within the controller scope."""
        raise NotImplementedError

    @property
    def dtype(self):
        """The data type as used by numpy."""
        raise NotImplementedError

    @property
    def shape(self):
        """The data shape as used by numpy."""
        raise NotImplementedError

    # Methods

    def create_acquisition_device(self, scan_pars, **settings):
        """Instanciate the corresponding acquisition device."""
        raise NotImplementedError

    # Extra logic

    @property
    def fullname(self):
        """A unique name within the session scope.

        The standard implementation defines it as:
        `<master_controller_name>.<controller_name>.<counter_name>`.
        """
        args = []
        # Master controller
        if self.master_controller is not None:
            args.append(self.master_controller.name)
        # Controller
        if self.controller is not None:
            args.append(self.controller.name)
        # Name
        args.append(self.name)
        return '.'.join(args)


class Counter(BaseCounter):
    GROUPED_READ_HANDLERS = weakref.WeakKeyDictionary()
    ACQUISITION_DEVICE_CLASS = NotImplemented

    def __init__(self, name,
                 grouped_read_handler=None,
                 conversion_function=None,
                 controller=None):
        self._name = name
        self._controller = controller
        self._conversion_function = conversion_function
        if grouped_read_handler:
            Counter.GROUPED_READ_HANDLERS[self] = grouped_read_handler

    # Standard interface

    @property
    def controller(self):
        return self._controller

    @property
    def name(self):
        return self._name

    @property
    def dtype(self):
        return numpy.float

    @property
    def shape(self):
        return ()

    # Default chain handling

    @classmethod
    def get_acquisition_device_class(cls):
        raise NotImplementedError

    def create_acquisition_device(self, scan_pars, **settings):
        read_handler = self.GROUPED_READ_HANDLERS.get(self, self)
        scan_pars.update(settings)
        return self.get_acquisition_device_class()(read_handler, **scan_pars)

    # Extra interface

    @property
    def conversion_function(self):
        return self._conversion_function

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class SamplingCounter(Counter):

    @classmethod
    def get_acquisition_device_class(cls):
        from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
        return SamplingCounterAcquisitionDevice

    class GroupedReadHandler(GroupedReadMixin):
        def read(self, *counters):
            """
            this method should return a list of read values in the same order
            as counters
            """
            raise NotImplementedError

    class ConvertValue(object):
        def __init__(self, grouped_read_handler):
            self.read = grouped_read_handler.read

        def __call__(self, *counters):
            return [cnt.conversion_function(x) if cnt.conversion_function else x
                    for x, cnt in zip(self.read(*counters), counters)]

    def __init__(self, name, controller,
                 grouped_read_handler=None, conversion_function=None):
        if grouped_read_handler is None and hasattr(controller, "read_all"):
            grouped_read_handler = DefaultSamplingCounterGroupedReadHandler(
                controller)

        if grouped_read_handler:
            if not isinstance(grouped_read_handler.read, self.ConvertValue):
                grouped_read_handler.read = self.ConvertValue(
                    grouped_read_handler)
        else:
            if callable(conversion_function):
                add_conversion_function(self, 'read', conversion_function)

        super(SamplingCounter, self).__init__(
            name, grouped_read_handler, conversion_function, controller)

    def read(self):
        try:
            grouped_read_handler = Counter.GROUPED_READ_HANDLERS[self]
        except KeyError:
            raise NotImplementedError
        else:
            grouped_read_handler.prepare(self)
            try:
                return grouped_read_handler.read(self)[0]
            finally:
                grouped_read_handler.stop(self)


def DefaultSamplingCounterGroupedReadHandler(
        controller, handlers=weakref.WeakValueDictionary()):
    class DefaultSamplingCounterGroupedReadHandler(
            SamplingCounter.GroupedReadHandler):
        """
        Default read all handler for controller which have read_all method
        """

        def read(self, *counters):
            return self.controller.read_all(*counters)
    return handlers.setdefault(
        controller, DefaultSamplingCounterGroupedReadHandler(controller))


class IntegratingCounter(Counter):

    @classmethod
    def get_acquisition_device_class(cls):
        from bliss.scanning.acquisition.counter import IntegratingCounterAcquisitionDevice
        return IntegratingCounterAcquisitionDevice

    @property
    def master_controller(self):
        return self._master_controller_ref()

    class GroupedReadHandler(GroupedReadMixin):
        def get_values(self, from_index, *counters):
            """
            this method should return a list of numpy arrays in the same order
            as the counter_name
            """
            raise NotImplementedError

    def __init__(self, name, controller, master_controller,
                 grouped_read_handler=None, conversion_function=None):
        if grouped_read_handler is None and hasattr(controller, "get_values"):
            grouped_read_handler = DefaultIntegratingCounterGroupedReadHandler(
                controller)

        if grouped_read_handler:
            class ConvertValues(object):
                def __init__(self, grouped_read_handler):
                    self.get_values = grouped_read_handler.get_values

                def __call__(self, from_index, *counters):
                    return [cnt.conversion_function(x) if cnt.conversion_function else x
                            for x, cnt in zip(self.get_values(from_index, *counters), counters)]
            grouped_read_handler.get_values = ConvertValues(
                grouped_read_handler)
        else:
            if callable(conversion_function):
                add_conversion_function(
                    self, 'get_values', conversion_function)

        super(IntegratingCounter, self).__init__(
            name, grouped_read_handler, conversion_function, controller)

        self._master_controller_ref = weakref.ref(master_controller)

    def get_values(self, from_index=0):
        """
        Overwrite in your class to provide a useful integrated counter class

        This method is called after the prepare and start on the master handler.
        This method can block until the data is ready or not and return empty data.
        When data is ready should return the data from the acquisition
        point **from_index**
        """
        raise NotImplementedError


def DefaultIntegratingCounterGroupedReadHandler(
        controller, handlers=weakref.WeakValueDictionary()):
    class DefaultIntegratingCounterGroupedReadHandler(
            IntegratingCounter.GroupedReadHandler):
        """
        Default read all handler for controller which have get_values method
        """

        def get_values(self, from_index, *counters):
            return [cnt.conversion_function(x) if cnt.conversion_function else x for x, cnt in
                    zip(self.controller.get_values(from_index, *counters), counters)]
    return handlers.setdefault(
        controller, DefaultIntegratingCounterGroupedReadHandler(controller))
