# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import time
import warnings
import functools
import gevent
import collections
from gevent import event
from bliss.common.event import dispatcher
from ..chain import AcquisitionDevice, AcquisitionChannel
from bliss.common.measurement import SamplingMode
from bliss.common.utils import all_equal
from collections import namedtuple
from datetime import datetime


def _get_group_reader(counters):
    readers = set(cnt.read_handler for cnt in counters)

    if len(set(readers)) != 1:
        raise RuntimeError(
            f"Counters {', '.join(cnt.name for cnt in counters)} do not belong to the same group read handler"
        )
    else:
        reader = readers.pop()

    if reader is None:
        raise RuntimeError(
            f"Cannot find a reader for counter(s): {', '.join(cnt.name for cnt in counters)}"
        )

    return reader


class BaseCounterAcquisitionDevice(AcquisitionDevice):
    def __init__(
        self,
        counters,  # _or_groupreadhandler,
        count_time,
        npoints,
        prepare_once,
        start_once,
        **unused_keys,
    ):
        reader = _get_group_reader(counters)

        AcquisitionDevice.__init__(
            self,
            reader,
            npoints=npoints,
            trigger_type=AcquisitionDevice.SOFTWARE,
            prepare_once=prepare_once,
            start_once=start_once,
        )

        self._reader = reader
        self.__count_time = count_time
        self._counters = collections.defaultdict(list)
        self._nb_acq_points = 0

        for cnt in counters:
            self.add_counter(cnt)

    @property
    def count_time(self):
        return self.__count_time

    def _do_add_counter(self, counter):
        chan_name = f"{self._reader.fullname}:{counter.name}"
        self.channels.append(
            AcquisitionChannel(
                chan_name, counter.dtype, counter.shape, unit=counter.unit
            )
        )
        self._counters[counter].append(self.channels[-1])

    def add_counter(self, counter):
        if counter in self._counters:
            return
        reader = _get_group_reader([counter])
        if reader != self._reader:
            raise RuntimeError(
                f"Cannot add counter {counter.name}: reader does not correspond to already added counters"
            )
        self._do_add_counter(counter)

    def _emit_new_data(self, data):
        self.channels.update_from_iterable(data)

    def fill_meta_at_scan_init(self, scan_meta):
        tmp_dict = {}

        def new_nx_collection(d, x):
            return d.setdefault(x, {"NX_class": "NXcollection"})

        for cnt in self._counters:
            name, _, _ = cnt.fullname.rpartition(":")
            det_name, _, name = name.partition(":")
            d = tmp_dict.setdefault(det_name, {"NX_class": "NXdetector"})
            if name:
                d = functools.reduce(new_nx_collection, name.split(":"), d)
            d.update(cnt.get_metadata())
        scan_meta.instrument.set(self, tmp_dict)


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
        SamplingMode.INTEGRATE_STATS: lambda acc_value, statistics, samples, nb_read, count_time: numpy.array(
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

    stats_nt = namedtuple(
        "SamplingCounterStatistics", "mean N std var min max p2v count_time timestamp"
    )

    def __init__(
        # self, counters_or_groupreadhandler, count_time=None, npoints=1, **unused_keys
        self,
        *counters,
        count_time=None,
        npoints=1,
        **unused_keys,
    ):
        """
        Helper to manage acquisition of a sampling counter.

        counters_or_groupreadhandler -- can be a list,tuple of SamplingCounter or
        a group_read_handler
        count_time -- the master integration time.
        Other keys are:
          * npoints -- number of points for this acquisition (0: endless acquisition)
        """

        if any([x in ["prepare_once", "start_once"] for x in unused_keys.keys()]):
            warnings.warn(
                "SamplingCounterAcquisitionDevice: prepare_once or start_once"
                "flags will be ignored"
            )

        start_once = npoints > 0
        npoints = max(1, npoints)

        self._event = event.Event()
        self._stop_flag = False
        self._ready_event = event.Event()
        self._ready_event.set()

        # self.mode_helpers will be populated with the `mode_lambdas`
        # according to the counters involved in the acquistion. One
        # entry per counter, order matters!
        self.mode_helpers = list()

        # Will be set to True when all counters associated to the
        # acq device are in SamplingMode.SINGLE. In this case
        # acquisition will not run in sampling loop but only
        # read one single value
        self._SINGLE_COUNT = False

        BaseCounterAcquisitionDevice.__init__(
            self,
            counters,
            count_time,
            npoints,
            True,  # prepare_once
            start_once,  # start_once
        )

    def _do_add_counter(self, counter):
        super()._do_add_counter(counter)  # add the 'default' counter (mean)

        self.mode_helpers.append(
            SamplingCounterAcquisitionDevice.mode_lambdas[counter.mode]
        )

        # helper to create AcquisitionChannels
        AC = lambda name_suffix, unit: AcquisitionChannel(
            f"{self._reader.fullname}:{counter.name}_{name_suffix}",
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
        elif counter.mode == SamplingMode.SAMPLES:
            self.channels.append(
                AcquisitionChannel(
                    f"{self._reader.fullname}:{counter.name}_samples",
                    counter.dtype,
                    counter.shape + (1,),
                    unit=counter.unit,
                )
            )
            self._counters[counter].append(self.channels[-1])

    def prepare(self):
        self._reader.prepare(*self._counters)

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

        self._reader.start(*self._counters)

    def stop(self):
        self._reader.stop(*self._counters)

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
                        self._reader._read(*self._counters), dtype=numpy.double, ndmin=1
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
                    self._reader._read(*self._counters), dtype=numpy.double, ndmin=1
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
                if c.mode == SamplingMode.INTEGRATE_STATS:
                    # apply error propagation laws to correct stats
                    # with time normalize values
                    st = self.STATS_to_INTEGRATE_STATS(st, self.count_time)
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
        if count < 2:
            return SamplingCounterAcquisitionDevice.stats_nt(
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
            return SamplingCounterAcquisitionDevice.stats_nt(
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

    @staticmethod
    def STATS_to_INTEGRATE_STATS(st, count_time):
        # apply error propagation laws to correct stats
        # with time normalize values
        st = numpy.array(st, dtype=numpy.object)
        # "mean N std var min max p2v count_time timestamp",
        st[:7] = st[:7] * [
            count_time,
            1,
            count_time,
            count_time * count_time,
            count_time,
            count_time,
            count_time,
        ]
        return SamplingCounterAcquisitionDevice.stats_nt(*st)


class IntegratingCounterAcquisitionDevice(BaseCounterAcquisitionDevice):
    # def __init__(self, counters_or_groupreadhandler, count_time=None, **unused_keys):
    def __init__(self, *counters, count_time=None, **unused_keys):

        if any(
            [x in ["npoints", "prepare_once", "start_once"] for x in unused_keys.keys()]
        ):
            warnings.warn(
                "IntegratingCounterAcquisitionDevice: npoints, prepare_once or "
                "start_once flags will be overwritten by master controller"
            )

        BaseCounterAcquisitionDevice.__init__(
            self,
            counters,
            count_time=count_time,
            npoints=None,
            prepare_once=None,
            start_once=None,
        )

    @AcquisitionDevice.parent.setter
    def parent(self, p):
        self._AcquisitionDevice__parent = p
        self._AcquisitionDevice__npoints = p.npoints
        self._AcquisitionDevice__prepare_once = p.prepare_once
        self._AcquisitionDevice__start_once = p.start_once

    def prepare(self):
        self._nb_acq_points = 0
        self._stop_flag = False
        self._reader.prepare(*self._counters)

    def start(self):
        self._reader.start(*self._counters)

    def stop(self):
        self._reader.stop(*self._counters)
        self._stop_flag = True

    def trigger(self):
        pass

    def _read_data(self, from_index):
        return self._reader._get_values(from_index, *self._counters)

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
