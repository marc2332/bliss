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
from bliss.common.utils import all_equal, apply_vectorized


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
            )

        self.__grouped_read_counters_list.append(counter)
        self.channels.append(
            AcquisitionChannel(
                counter, counter.name, counter.dtype, counter.shape, unit=counter.unit
            )
        )

    def _emit_new_data(self, data):
        self.channels.update_from_iterable(data)


class SamplingCounterAcquisitionDevice(BaseCounterAcquisitionDevice):
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

        for cnt in counters:
            self.add_counter(cnt)

    def prepare(self):
        self.device.prepare(*self.grouped_read_counters)

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

        # mode dependent helpers that are evaluated once per point
        mode_lambdas = {
            SamplingMode.SIMPLE_AVERAGE: lambda acc_value, acc_read_time, nb_read, count_time: acc_value
            / nb_read,
            SamplingMode.INTEGRATE: lambda acc_value, acc_read_time, nb_read, count_time: (
                acc_value / nb_read
            )
            * count_time,
        }

        mode_helpers = list()
        for c in self.channels:
            mode_helpers.append(mode_lambdas[c.acq_device.mode])
        mode_helpers = numpy.array(mode_helpers)

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
            acc_value = numpy.zeros((len(self.channels),), dtype=numpy.double)
            stop_time = trig_time + self.count_time or 0

            # Counter integration loop
            while not self._stop_flag:
                start_read = time.time()
                read_value = numpy.array(
                    self.device.read(*self.grouped_read_counters), dtype=numpy.double
                )
                end_read = time.time()

                acc_value += read_value

                nb_read += 1
                acc_read_time += end_read - start_read

                current_time = time.time()
                if (current_time + (acc_read_time / nb_read)) > stop_time:
                    break
                gevent.sleep(0)  # to be able to kill the task
            self._nb_acq_points += 1

            # apply the necessary operation per channel to convert the read data depending on the mode of each channel
            data = apply_vectorized(
                mode_helpers, acc_value, acc_read_time, nb_read, self.count_time
            )

            self._emit_new_data(data)

            self._ready_event.set()


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
