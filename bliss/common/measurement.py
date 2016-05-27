# -*- coding: utf-8 -*-

"""
Measurement and counter module

Examples::

  from random import random

  from bliss.common.measurement import CounterBase

  # Write a new counter and counting

  class MyCounter(CounterBase):
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

  class MyCounter(CounterBase):

    Measurement = SingleMeasurement

    def read(self):
      return random()*1000.
"""

# run tests for this module from the bliss root directory with:
# python -m unittest discover -s tests/acquisition -v

import time

import six
import numpy


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


class CounterBase(object):
    """
    Base class for counters.
    When defining a new sub-class you are only obliged to overwrite the
    :meth:`read` method which should return the value that was read.

    If your read source also provides a timestamp (ex: tango), you can
    overwrite the :meth:`read_timestamp` method instead. It should
    return a tuple with a value and a timestamp.

    By default, counting uses the :class:`Measurement` class which will read
    read as fast as it can. The measurement value obtained from a :meth:`count`
    will then be an average of all values.

    You can override the default behavior for your own class by pointing
    `Measurement` to your desired class (the measurement class must be able
    to be constructed without arguments).

    You can also override the behavior of a specific :meth:`count` call
    by providing a measurement argument.
    """

    #: default measurement class
    Measurement = Measurement

    def __init__(self, name):
        self.__name = name

    @property
    def name(self):
        return self.__name

    def read(self):
        """Overwrite in your class to provide a useful counter class"""
        raise NotImplementedError

    def read_timestamp(self):
        """
        Read the value and timestamp. Default implementation calls
        :meth:`read` and a timestamp just after the read.
        """
        value = self.read()
        return value, time.time()

    def count(self, time=None, measurement=None):
        """
        Count for the specified time.

        :return: a measurement object representing the count that was made
        :rtype: :class:`MeasurementBase`
        """
        meas = measurement or self.Measurement()
        for reading in meas(time):
            reading.value, reading.timestamp = self.read_timestamp()
        return meas
