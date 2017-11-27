# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import time
import gevent
from gevent import event
from bliss.common.event import dispatcher
from ..chain import AcquisitionDevice, AcquisitionChannel
from bliss.common.measurement import GroupedReadMixin
from bliss.common.utils import all_equal


class BaseCounterAcquisitionDevice(AcquisitionDevice):
    def __init__(self, counter, count_time, **keys):
        npoints = max(1, keys.pop('npoints', 1))
        prepare_once = keys.pop('prepare_once', True)
        start_once = keys.pop('start_once', npoints > 1)

        AcquisitionDevice.__init__(self, counter, counter.name, "zerod",
                                   npoints=npoints,
                                   trigger_type=AcquisitionDevice.SOFTWARE,
                                   prepare_once=prepare_once,
                                   start_once=start_once)

        self.__count_time = count_time
        self.__grouped_read_counters_list = list()
        self.__counter_names = list()
        self._nb_acq_points = 0

        if not isinstance(counter, GroupedReadMixin):
            self.channels.append(AcquisitionChannel(
                counter.name, numpy.double, (1,)))
            self.__counter_names.append(counter.name)

    @property
    def count_time(self):
        return self.__count_time

    @property
    def grouped_read_counters(self):
        return self.__grouped_read_counters_list

    @property
    def counter_names(self):
        return self.__counter_names

    def add_counter(self, counter):
        if not isinstance(self.device, GroupedReadMixin):
            raise RuntimeError(
                "Cannot add counter to single-read counter acquisition device")

        self.__grouped_read_counters_list.append(counter)
        self.__counter_names.append(counter.name)
        self.channels.append(AcquisitionChannel(
            counter.name, numpy.double, (1,)))

    def _emit_new_data(self, data):
        channel_data = dict([(name, data[i])
                             for i, name in enumerate(self.counter_names)])
        dispatcher.send("new_data", self, {"channel_data": channel_data})


class SamplingCounterAcquisitionDevice(BaseCounterAcquisitionDevice):
    SIMPLE_AVERAGE, TIME_AVERAGE, INTEGRATE = range(3)

    def __init__(self, counter, count_time=None, mode=SIMPLE_AVERAGE, **keys):
        """
        Helper to manage acquisition of a sampling counter.

        count_time -- the master integration time.
        mode -- three mode are available *SIMPLE_AVERAGE* (the default)
        which sum all the sampling values and divide by the number of read value.
        the *TIME_AVERAGE* which sum all integration  then divide by the sum
        of time spend to measure all values. And *INTEGRATION* which sum all integration
        and then normalize it when the *count_time*.
        Other keys are:
          * npoints -- number of point for this acquisition
          * prepare_once --
          * start_once --
        """
        BaseCounterAcquisitionDevice.__init__(
            self, counter, count_time, **keys)

        self._event = event.Event()
        self._stop_flag = False
        self._ready_event = event.Event()
        self._ready_flag = True
        self.__mode = mode

    @property
    def mode(self):
        return self.__mode

    @mode.setter
    def mode(self, value):
        self.__mode = value

    def prepare(self):
        self.device.prepare(*self.grouped_read_counters)

    def start(self):
        self._nb_acq_points = 0
        self._stop_flag = False
        self._ready_flag = True
        self._event.clear()

        self.device.start(*self.grouped_read_counters)

    def stop(self):
        self.device.stop(*self.grouped_read_counters)

        self._stop_flag = True
        self._trig_time = None
        self._event.set()

    def trigger(self):
        self._trig_time = time.time()
        self._event.set()

    def wait_ready(self):
        """
        will wait until the last triggered point is read
        """
        while not self._ready_flag:
            self._ready_event.wait()
            self._ready_event.clear()

    def reading(self):
        while self._nb_acq_points < self.npoints:
            # trigger wait
            self._event.wait()
            self._event.clear()
            self._ready_flag = False
            trig_time = self._trig_time
            if trig_time is None:
                continue
            if self._stop_flag:
                break

            nb_read = 0
            acc_read_time = 0
            acc_value = numpy.zeros(
                (len(self.counter_names),), dtype=numpy.double)
            stop_time = trig_time + self.count_time or 0
            # Counter integration loop
            while not self._stop_flag:
                start_read = time.time()
                read_value = numpy.array(self.device.read(
                    *self.grouped_read_counters), dtype=numpy.double)
                end_read = time.time()
                read_time = end_read - start_read

                if self.__mode == SamplingCounterAcquisitionDevice.TIME_AVERAGE:
                    acc_value += read_value * (end_read - start_read)
                else:
                    acc_value += read_value

                nb_read += 1
                acc_read_time += end_read - start_read

                current_time = time.time()
                if (current_time + (acc_read_time / nb_read)) > stop_time:
                    break
                gevent.sleep(0)  # to be able to kill the task
            self._nb_acq_points += 1
            if self.__mode == SamplingCounterAcquisitionDevice.TIME_AVERAGE:
                data = acc_value / acc_read_time
            else:
                data = acc_value / nb_read

            if self.__mode == SamplingCounterAcquisitionDevice.INTEGRATE:
                data *= self.count_time

            self._emit_new_data(data)

            self._ready_flag = True
            self._ready_event.set()


class IntegratingCounterAcquisitionDevice(BaseCounterAcquisitionDevice):
    def __init__(self, counter, count_time=None, **keys):
        BaseCounterAcquisitionDevice.__init__(
            self, counter, count_time, **keys)

    def prepare(self):
        self.device.prepare(*self.grouped_read_counters)

    def start(self):
        self._nb_acq_points = 0
        self._stop_flag = False

        self.device.start(*self.grouped_read_counters)

    def stop(self):
        self.device.stop(*self.grouped_read_counters)
        self._stop_flag = True

    def trigger(self):
        pass

    def _read_data(self, from_index):
        if self.grouped_read_counters:
            return self.device.get_values(from_index, *self.grouped_read_counters)
        else:
            return [numpy.array(self.device.get_value(from_index), dtype=numpy.double)]

    def reading(self):
        from_index = 0
        while self._nb_acq_points < self.npoints and not self._stop_flag:
            data = self._read_data(from_index)
            if not all_equal([len(d) for d in data]):
                raise RuntimeError("Read data can't have different sizes")
            if len(data[0]) > 0:
                from_index += len(data[0])
                self._nb_acq_points += len(data[0])
                self._emit_new_data(data)
                gevent.idle()
            else:
                gevent.sleep(self.count_time / 2.)
