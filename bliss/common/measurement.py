# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# run tests for this module from the bliss root directory with:
# python -m unittest discover -s tests/acquisition -v

import time

import six
import numpy
import weakref

from bliss.common.utils import add_conversion_function


class GroupedReadMixin(object):
    def __init__(self, controller):
        self.__controller_ref = weakref.ref(controller)

    @property
    def name(self):
        return self.controller.name

    @property
    def controller(self):
        return self.__controller_ref()

    @property
    def id(self):
        return id(self.controller)

    def prepare(self, *counters):
        pass

    def start(self, *counters):
        pass

    def stop(self, *counters):
        pass


class Counter(object):
    GROUPED_READ_HANDLERS = weakref.WeakKeyDictionary()

    def __init__(self, name,
                 grouped_read_handler = None, conversion_function = None):
        self.__name = name

        if grouped_read_handler:
            Counter.GROUPED_READ_HANDLERS[self] = grouped_read_handler

        self.__conversion_function = conversion_function

    @property
    def name(self):
        return self.__name

    @property
    def dtype(self):
        return numpy.float

    @property
    def shape(self):
        return ()

    @property
    def conversion_function(self):
        return self.__conversion_function

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class SamplingCounter(Counter):
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
            return [cnt.conversion_function(x) if cnt.conversion_function else x for x, cnt in \
                    zip(self.read(*counters), counters)]

    def __init__(self, name, controller,
                 grouped_read_handler = None,conversion_function = None):
        if grouped_read_handler is None and hasattr(controller, "read_all"):
            grouped_read_handler = DefaultSamplingCounterGroupedReadHandler(controller)

        if grouped_read_handler:
            if not isinstance(grouped_read_handler.read,self.ConvertValue):
                grouped_read_handler.read = self.ConvertValue(grouped_read_handler)
        else:
            if callable(conversion_function):
                add_conversion_function(self, 'read', conversion_function)

        Counter.__init__(self, name, grouped_read_handler, conversion_function)

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

def DefaultSamplingCounterGroupedReadHandler(controller, handlers=weakref.WeakValueDictionary()):
    class DefaultSamplingCounterGroupedReadHandler(SamplingCounter.GroupedReadHandler):
        """
        Default read all handler for controller which have read_all method
        """
        def read(self, *counters):
            return self.controller.read_all(*counters)
    return handlers.setdefault(controller, DefaultSamplingCounterGroupedReadHandler(controller))

class IntegratingCounter(Counter):
    class GroupedReadHandler(GroupedReadMixin):
        def get_values(self, from_index, *counters):
            """
            this method should return a list of numpy arrays in the same order
            as the counter_name
            """
            raise NotImplementedError

    def __init__(self, name, controller, acquisition_controller,
                 grouped_read_handler = None, conversion_function = None):
        if grouped_read_handler is None and hasattr(controller, "get_values"):
            grouped_read_handler = DefaultIntegratingCounterGroupedReadHandler(controller)

        if grouped_read_handler:
            class ConvertValues(object):
                def __init__(self, grouped_read_handler):
                    self.get_values = grouped_read_handler.get_values
                def __call__(self, from_index, *counters):
                    return [cnt.conversion_function(x) if cnt.conversion_function else x for x, cnt in \
                            zip(self.get_values(from_index, *counters), counters)]
            grouped_read_handler.get_values = ConvertValues(grouped_read_handler)
        else:
            if callable(conversion_function):
                add_conversion_function(self, 'get_values', conversion_function)

        Counter.__init__(self, name, grouped_read_handler, conversion_function)

        self.__acquisition_controller_ref = weakref.ref(acquisition_controller)

    def get_values(self, from_index=0):
        """
        Overwrite in your class to provide a useful integrated counter class

        this method is called after the prepare and start on the master handler.
        this method can block until the data is ready or not and return empty data.
        When data is ready should return the data from the acquisition
        point **from_index**
        """
        raise NotImplementedError

    @property
    def acquisition_controller(self):
        return self.__acquisition_controller_ref()

def DefaultIntegratingCounterGroupedReadHandler(controller, handlers=weakref.WeakValueDictionary()):
    class DefaultIntegratingCounterGroupedReadHandler(IntegratingCounter.GroupedReadHandler):
        """
        Default read all handler for controller which have get_values method
        """
        def get_values(self, from_index, *counters):
            return [cnt.conversion_function(x) if cnt.conversion_function else x for x,cnt in \
                    zip(self.controller.get_values(*counters),counters)]
    return handlers.setdefault(controller, DefaultIntegratingCounterGroupedReadHandler(controller))
