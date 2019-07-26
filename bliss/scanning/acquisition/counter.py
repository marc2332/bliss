# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import time
import warnings
import gevent
from gevent import event
from bliss.common.event import dispatcher
from ..chain import AcquisitionDevice, AcquisitionChannel
from bliss.common.measurement import GroupedReadMixin, Counter, SamplingMode
from bliss.common.utils import all_equal
from collections import namedtuple
from datetime import datetime


def _get_group_reader(counters_or_groupreadhandler):
    try:
        list_iter = iter(counters_or_groupreadhandler)
    except TypeError:
        if isinstance(counters_or_groupreadhandler, GroupedReadMixin):
            return counters_or_groupreadhandler, []

        return (
            Counter.GROUPED_READ_HANDLERS.get(
                counters_or_groupreadhandler, counters_or_groupreadhandler
            ),
            [counters_or_groupreadhandler],
        )
    else:
        first_counter = next(list_iter)
        reader = Counter.GROUPED_READ_HANDLERS.get(first_counter)
        for cnt in list_iter:
            cnt_reader = Counter.GROUPED_READ_HANDLERS.get(cnt)
            if cnt_reader != reader:
                raise RuntimeError(
                    "Counters %s doesn't belong to the same group"
                    % counters_or_groupreadhandler
                )
        return reader, counters_or_groupreadhandler


class BaseCounterAcquisitionDevice(AcquisitionDevice):
    def __init__(
        self, counter, count_time, npoints, prepare_once, start_once, **unused_keys
    ):
        AcquisitionDevice.__init__(
            self,
            counter,
            counter.name,
            npoints=npoints,
            trigger_type=AcquisitionDevice.SOFTWARE,
            prepare_once=prepare_once,
            start_once=start_once,
        )

        self.__count_time = count_time
        self.__grouped_read_counters_list = list()
        self._nb_acq_points = 0

        if not isinstance(counter, GroupedReadMixin):
            self.channels.append(
                AcquisitionChannel(
                    counter,
                    counter.name,
                    counter.dtype,
                    counter.shape,
                    unit=counter.unit,
                )
            )

    @property
    def count_time(self):
        return self.__count_time

    @property
    def grouped_read_counters(self):
        return self.__grouped_read_counters_list

    def add_counter(self, counter):
        if not isinstance(self.device, GroupedReadMixin):
            # Ignore if the counter is already the provided device
            if self.device == counter:
                return
            raise RuntimeError(
                "Cannot add counter to single-read counter acquisition device"
            )  ##### What is this for??????

        self.__grouped_read_counters_list.append(counter)
        self.channels.append(
            AcquisitionChannel(
                counter, counter.name, counter.dtype, counter.shape, unit=counter.unit
            )
        )

    def _emit_new_data(self, data):
        self.channels.update_from_iterable(data)


class SamplingCounterAcquisitionDevice(BaseCounterAcquisitionDevice):

    # mode dependent helpers that are evaluated once per point
    mode_lambdas = {
        SamplingMode.MEAN: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
            [acc_value / nb_read]
        ),
        SamplingMode.INTEGRATE: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
            [(acc_value / nb_read)]
        )
        * count_time,
        SamplingMode.STATS: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
            tuple(statistics)[:7]
        ),
        SamplingMode.SINGLE: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
            [samples]
        ),
        SamplingMode.SAMPLES: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
            [acc_value / nb_read, samples]
        ),
        SamplingMode.LAST: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
            [samples]
        ),
    }

    def __init__(
        self, counters_or_groupreadhandler, count_time=None, npoints=1, **unused_keys
    ):
        """
        Helper to manage acquisition of a sampling counter.

        counters_or_groupreadhandler -- can be a list,tuple of SamplingCounter or
        a group_read_handler
        count_time -- the master integration time.
        Other keys are:
          * npoints -- number of point for this acquisition (0: endless acquisition)
        """

        if any([x in ["prepare_once", "start_once"] for x in unused_keys.keys()]):
            warnings.warn(
                "SamplingCounterAcquisitionDevice: prepare_once or start_once"
                "flags will be ignored"
            )

        start_once = npoints > 0
        npoints = max(1, npoints)

        reader, counters = _get_group_reader(counters_or_groupreadhandler)
        BaseCounterAcquisitionDevice.__init__(
            self,
            reader,
            count_time,
            npoints,
            True,  # prepare_once
            start_once,  # start_once
        )

        self._event = event.Event()
        self._stop_flag = False
        self._ready_event = event.Event()
        self._ready_event.set()

        # self.mode_helpers will be populated with the `mode_lambdas`
        # according to the counters involved in the aquistion. One
        # entry per counter, order matters!
        self.mode_helpers = list()

        ### TODO: To be removed with Matias merge request
        ### to be harmonized with Matias code... here we use a dict
        ### while Mathis uses a list()
        # dict that contains counters handled by this acq_device as keys
        # and list of assiciated channels as value
        self._counters = dict()

        # Will be set to True when all counters associated to the
        # acq device are in SamplingMode.SINGLE. In this case
        # aquisition will not run in sampling loop but only
        # read one single value
        self._SINGLE_COUNT = False

        for cnt in counters:
            self.add_counter(cnt)

    def add_counter(self, counter):
        if counter in self._counters:
            return
        super().add_counter(counter)

        # initialize the entry in self._counters with the **main** channel that
        # is created by the base class
        self._counters[counter] = [self.channels[-1]]  # mean value

        self.mode_helpers.append(
            SamplingCounterAcquisitionDevice.mode_lambdas[counter.mode]
        )

        # helper to create AcquisitionChannels
        AC = lambda name_suffix, unit: AcquisitionChannel(
            counter,
            counter.name + "_" + name_suffix,
            counter.dtype,
            counter.shape,
            unit=unit,
        )

        if counter.mode == SamplingMode.STATS:
            # N
            self.channels.append(AC("N", "#"))
            self._counters[counter].append(self.channels[-1])

            # std
            self.channels.append(AC("std", counter.unit))
            self._counters[counter].append(self.channels[-1])

            # var
            self.channels.append(
                AC("var", counter.unit + "^2" if counter.unit is not None else None)
            )
            self._counters[counter].append(self.channels[-1])

            # min
            self.channels.append(AC("min", counter.unit))
            self._counters[counter].append(self.channels[-1])

            # max
            self.channels.append(AC("max", counter.unit))
            self._counters[counter].append(self.channels[-1])

            # p2v
            self.channels.append(AC("p2v", counter.unit))
            self._counters[counter].append(self.channels[-1])

        if counter.mode == SamplingMode.SAMPLES:
            self.channels.append(
                AcquisitionChannel(
                    counter,
                    counter.name + "_samples",
                    counter.dtype,
                    counter.shape + (1,),
                    unit=counter.unit,
                )
            )
            self._counters[counter].append(self.channels[-1])

    def prepare(self):
        self.device.prepare(*self.grouped_read_counters)

        # check modes to see if sampling loop is needed or not
        if all(
            numpy.array([c.mode for c in self._counters.keys()]) == SamplingMode.SINGLE
        ):
            self._SINGLE_COUNT = True

    def start(self):
        self._nb_acq_points = 0
        self._stop_flag = False
        self._ready_event.set()
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

    def trigger_ready(self):
        return self._ready_event.is_set()

    def wait_ready(self):
        """
        will wait until the last triggered point is read
        """
        self._ready_event.wait()

    def reading(self):
        if len(self.channels) == 0:
            return

        while not self._stop_flag and self._nb_acq_points < self.npoints:
            # trigger wait
            self._event.wait()
            self._event.clear()
            self._ready_event.clear()
            trig_time = self._trig_time
            if trig_time is None:
                continue
            if self._stop_flag:
                break

            nb_read = 0
            acc_read_time = 0
            acc_value = 0
            stop_time = trig_time + self.count_time or 0

            # tmp buffer for rolling statistics
            # Entries per counter:
            # 0:count, 1:mean, 2:M2 , 3:min, 4:max
            statistics = numpy.array(
                [[0, 0, 0, numpy.nan, numpy.nan]] * len(self._counters)
            )

            # empty structur to save samples
            # in SamplingMode.SAMPLES: list of indidual samples
            # in SamplingMode.SINGLE: first sample
            # in SamplingMode.LAST: last sample
            samples = [[]] * len(self._counters)

            if not self._SINGLE_COUNT:
                # Counter integration loop
                while not self._stop_flag:
                    start_read = time.time()
                    read_value = numpy.array(
                        self.device.read(*self.grouped_read_counters),
                        dtype=numpy.double,
                        ndmin=1,
                    )
                    end_read = time.time()

                    acc_value += read_value

                    nb_read += 1
                    acc_read_time += end_read - start_read

                    for i, c in enumerate(self._counters.keys()):
                        statistics[i] = self.rolling_stats_update(
                            statistics[i], read_value[i]
                        )
                        if c.mode == SamplingMode.SAMPLES:
                            samples[i].append(read_value[i])

                        elif c.mode == SamplingMode.SINGLE and samples[i] == []:
                            samples[i] = read_value[i]

                        elif c.mode == SamplingMode.LAST:
                            samples[i] = read_value[i]

                    current_time = time.time()
                    if (current_time + (acc_read_time / nb_read)) > stop_time:
                        break
                    gevent.sleep(0)  # to be able to kill the task
            else:
                # SINGLE_COUNT case
                acc_value = numpy.array(
                    self.device.read(*self.grouped_read_counters),
                    dtype=numpy.double,
                    ndmin=1,
                )
                samples = acc_value

                acc_read_time = 0
                nb_read = 1
                current_time = time.time()

            self._nb_acq_points += 1

            # Deal with statistics
            stats = list()
            for i, c in enumerate(self._counters.keys()):
                st = self.rolling_stats_finalize(
                    statistics[i], self.count_time, current_time
                )
                c._statistics = st
                stats.append(st)

            # apply the necessary operation per channel to convert the read data depending on the mode of each channel
            data = self.apply_vectorized(
                self.mode_helpers, acc_value, stats, samples, nb_read, self.count_time
            )

            for counter, channel_list in self._counters.items():
                if counter.mode == SamplingMode.SAMPLES:
                    samp_chan_index = self.channels.index(channel_list[1])
                    data[samp_chan_index] = numpy.array(data[samp_chan_index])
                    channel_list[1].shape = data[samp_chan_index].shape

            self._emit_new_data(data)

            self._ready_event.set()

    @staticmethod
    def apply_vectorized(functions, data, stats, samples, *params):
        """
        apply_vectorized: helper to apply a 'list' of functions provided as numpy array per element on
        a numpy array containing data.  H
        """
        return numpy.concatenate(
            [
                f(d, s, samp, *params)
                for f, d, s, samp in zip(functions, data, stats, samples)
            ]
        ).ravel()

    ### functions for rolling calculation of statistics (Welford's online algorithm)
    ### based on implementation given at https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance

    # for a new value newValue, compute the new count, new mean, the new M2.
    # mean accumulates the mean of the entire dataset
    # M2 aggregates the squared distance from the mean
    # count aggregates the number of samples seen so far
    @staticmethod
    def rolling_stats_update(existingAggregate, newValue):
        (count, mean, M2, Min, Max) = existingAggregate
        count += 1
        delta = newValue - mean
        mean += delta / count
        delta2 = newValue - mean
        M2 += delta * delta2
        Min = numpy.nanmin((Min, newValue))
        Max = numpy.nanmax((Max, newValue))

        return (count, mean, M2, Min, Max)

    # retrieve the mean, variance and sample variance (M2/(count - 1)) from an aggregate
    @staticmethod
    def rolling_stats_finalize(existingAggregate, count_time=None, timest=None):
        (count, mean, M2, Min, Max) = existingAggregate
        (mean, variance) = (mean, M2 / count)
        stats = namedtuple(
            "SamplingCounterStatistics",
            "mean N std var min max p2v count_time timestamp",
        )
        if count < 2:
            return stats(
                mean,
                count,
                numpy.nan,
                numpy.nan,
                numpy.nan,
                numpy.nan,
                numpy.nan,
                count_time,
                timest,
            )
        else:
            timest = str(datetime.fromtimestamp(timest)) if timest != None else None
            return stats(
                mean,
                numpy.int(count),
                numpy.sqrt(variance),
                variance,
                Min,
                Max,
                Max - Min,
                count_time,
                timest,
            )


class IntegratingCounterAcquisitionDevice(BaseCounterAcquisitionDevice):
    def __init__(self, counters_or_groupreadhandler, count_time=None, **unused_keys):

        if any(
            [x in ["npoints", "prepare_once", "start_once"] for x in unused_keys.keys()]
        ):
            warnings.warn(
                "IntegratingCounterAcquisitionDevice: npoints, prepare_once or "
                "start_once flags will be overwritten by master controller"
            )

        reader, counters = _get_group_reader(counters_or_groupreadhandler)
        BaseCounterAcquisitionDevice.__init__(
            self, reader, count_time, npoints=None, prepare_once=None, start_once=None
        )
        for cnt in counters:
            self.add_counter(cnt)

    @AcquisitionDevice.parent.setter
    def parent(self, p):
        self._AcquisitionDevice__parent = p
        self._AcquisitionDevice__npoints = p.npoints
        self._AcquisitionDevice__prepare_once = p.prepare_once
        self._AcquisitionDevice__start_once = p.start_once

    def prepare(self):
        self._nb_acq_points = 0
        self._stop_flag = False
        self.device.prepare(*self.grouped_read_counters)

    def start(self):
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
            return [numpy.array(self.device.get_values(from_index), dtype=numpy.double)]

    def reading(self):
        from_index = 0
        while (
            not self.npoints or self._nb_acq_points < self.npoints
        ) and not self._stop_flag:
            data = self._read_data(from_index)
            if not all_equal([len(d) for d in data]):
                raise RuntimeError("Read data can't have different sizes")
            if len(data[0]) > 0:
                from_index += len(data[0])
                self._nb_acq_points += len(data[0])
                self._emit_new_data(data)
                gevent.idle()
            else:
                gevent.sleep(self.count_time / 2.0)
