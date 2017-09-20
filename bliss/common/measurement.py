# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Measurement and counter module

Examples::

  from random import random

  from bliss.common.measurement import SamplingCounter

  # Write a new counter and counting

  class MyCounter(SamplingCounter):
    def read(self):
      return random()*1000.

  counter = MyCounter('r1')
  count_time = 0.1
  result = counter.count(count_time)

  print('Counted for {0}s: value={1.value}; nb_points={1.nb_points}'\
        .format(count_time, result))


  # Overwriting the default measurement for a specific count

  from bliss.common.measurement import SingleMeasurement

  result = counter.count(count_time, meaurement=SingleMeasurement())


  # Overwriting the default measurement for your counter class

  class MyCounter(SamplingCounter):

    Measurement = SingleMeasurement

    def read(self):
      return random()*1000.
"""

# run tests for this module from the bliss root directory with:
# python -m unittest discover -s tests/acquisition -v

import time

import six
import numpy
import weakref

class Reading(object):
    """Value yielded from a reading"""
    __slots__ = 'value', 'timestamp'

    def __init__(self):
      self.value = 0
      self.timestamp = 0


class MeasurementBase(object):
    """
    Base measurement class.
    Sub-class it by overwriting the :meth:`_count` and :meth:`value`.
    """
    __slots__ = '__running'

    @property
    def value(self):
        raise NotImplementedError

    def _count(self, acq_time):
        raise NotImplementedError

    def count(self, acq_time):
        if self.is_running():
            raise RuntimeError('measurement is already running')
        self.__running = True
        try:
            return self._count(acq_time)
        finally:
            self.__running = False

    def is_running(self):
        try:
            return self.__running
        except AttributeError:
            self.__running = False
        return self.__running

    def __call__(self, acq_time):
        return self.count(acq_time)


class SingleMeasurement(MeasurementBase):
    """
    Single measurement class. Disregard the acq_time and always do one
    and one only single read per count.
    """
    __slots__ = '__value'

    @property
    def value(self):
        return self.__value

    def _count(self, acq_time):
        reading = Reading()
        yield reading
        self.__value = reading.value


class Measurement(MeasurementBase):
    """
    Typical measurement: read as many points as possible. The measurement
    value is the average of all reads. You can also query the :meth:`sum`
    and the :meth:`nb_points`
    """
    __slots__ = '__sum', '__nb_points'

    def __init__(self):
        self.__sum = 0
        self.__nb_points = 0

    @property
    def sum(self):
        return self.__sum

    @property
    def average(self):
        if self.__nb_points == 0:
            return 0
        return self.__sum / self.__nb_points

    @property
    def nb_points(self):
        return self.__nb_points

    @property
    def value(self):
        return self.average

    def _add_value(self, value, timestamp):
        self.__nb_points += 1
        self.__sum += value

    def _count(self, acq_time):
        self.__sum = 0
        self.__nb_points = 0
        t0 = time.time()
        while True:
            last_acq_start_time = time.time()
            reading = Reading()
            yield reading
            last_acq_end_time = time.time()
            delta = last_acq_end_time - last_acq_start_time
            abs_acq_time = last_acq_end_time - t0
            timestamp = reading.timestamp or last_acq_start_time + delta/2.
            self._add_value(reading.value, timestamp)
            if acq_time is None or abs_acq_time >= acq_time:
                break

# just an alias
AverageMeasurement = Measurement


class FullMeasurement(Measurement):
    """
    Full measurement. Same as :class:`Measurement` but will also
    provide in :meth:`data` the 2D array of all reads. The first
    column of the array is the read value and the second column
    is its timestamp
    """
    __slots__ = '__data'

    def __init__(self):
        Measurement.__init__(self)
        self.__data = []

    @property
    def nb_points(self):
        return len(self.__data)

    @property
    def data(self):
        data = self.__data
        if self.is_running():
            return numpy.array(data)
        if isinstance(data, list):
            self.__data = data = numpy.array(data)
        # return a view of the data to avoid users messing
        # with the original shape or dtype
        return data[:]

    def _add_value(self, value, timestamp):
        Measurement._add_value(self, value, timestamp)
        self.__data.append((value, timestamp))

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

    def end(self, *counters):
        pass

class Counter(object):
    def __init__(self,name,controller,default_grouped_read_handler = None):
        self.__name = name
        if hasattr(controller,'read_all') and default_grouped_read_handler:
            self.__default_grouped_read_handler = default_grouped_read_handler(controller)
        else:
            self.__default_grouped_read_handler = None

    @property
    def name(self):
        return self.__name
    
    @property
    def controller(self):
        return self.__controller_ref() if self.__controller_ref is not None else None

    def grouped_read_handler(self):
        """
        Should return a handler which is has the interface of SamplingCounter.GroupedReadHandler.
        This Handler will be used to group counters to read all values at once.
        """
        if self.__default_grouped_read_handler:
            return self.__default_grouped_read_handler
        raise NotImplementedError


class SamplingCounter(Counter):
    class GroupedReadHandler(GroupedReadMixin):
        def read(self, *counters):
            """
            this method should return a list of reads values in the same order 
            as counters
            """
            raise NotImplementedError

    def __init__(self, name, controller):
        Counter.__init__(self,name,controller,DefaultSamplingCounterGroupedReadHandler)

    def read(self):
        handler = self.grouped_read_handler()
        try:
            handler.prepare(self)
            return handler.read_all(self)[0]
        finally:
            handler.end(self)


class DefaultSamplingCounterGroupedReadHandler(SamplingCounter.GroupedReadHandler):
    """
    Default read all handler for controller which have read_all method
    """
    def read(self, *counters):
        return self.controller.read_all(*counters)


class IntegratingCounter(Counter):
    class GroupedReadHandler(GroupedReadMixin):
        def get_values(self, from_index, *counters):
            """
            this method should return a list of reads values in the same order 
            as the counter_name
            """
            raise NotImplementedError

    """
    Base class for integrated counters.
    """
    def __init__(self, name, controller, acquisition_controller):
        Counter.__init__(self, name, controller, DefaultIntegratingCounterGroupedReadHandler)
        self.__acquisition_controller_ref = weakref.ref(acquisition_controller)

    def get_values(self, from_index=0):
        """
        Overwrite in your class to provide a useful integrated counter class

        this method is called after the prepare and start on the master handler.
        this method can block until the data is ready or not and return empty data.
        When data is ready should return the data from the acquisition
        point **from_point_index**
        """
        raise NotImplementedError

    @property
    def acquisition_controller(self):
        return self.__acquisition_controller_ref()

class DefaultIntegratingCounterGroupedReadHandler(IntegratingCounter.GroupedReadHandler):
    """
    Default read all handler for controller which have read_all method
    """
    def get_values(self, from_index, *counters):
        return self.controller.get_values(from_index, *counters)

