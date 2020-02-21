# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""CT2 (P201/C208) bliss acquisition master"""

import numpy
import gevent.event

from bliss.common import event
from bliss.scanning.chain import AcquisitionMaster
from bliss.scanning.acquisition.counter import IntegratingCounterAcquisitionSlave
from bliss.controllers.ct2.device import (
    AcqMode,
    AcqStatus,
    StatusSignal,
    PointNbSignal,
    ErrorSignal,
    DataSignal,
)


class CT2AcquisitionMaster(AcquisitionMaster):

    SoftTrigModes = AcqMode.IntTrigMulti, AcqMode.SoftTrigReadout

    def __init__(
        self,
        device,
        ctrl_params=None,
        npoints=1,
        acq_expo_time=1.,
        acq_point_period=None,
        acq_mode=AcqMode.IntTrigMulti,
        prepare_once=True,
        start_once=True,
    ):
        self._connected = False
        self.acq_expo_time = acq_expo_time
        self.acq_mode = acq_mode
        self.acq_point_period = acq_point_period
        self.first_trigger = None
        self.status = None
        self.last_point_ready = None
        self.last_error = None
        self._ready_event = gevent.event.Event()
        self._ready_event.set()
        if acq_mode in self.SoftTrigModes:
            trigger_type = self.SOFTWARE
        else:
            trigger_type = self.HARDWARE
        self.use_internal_clock = acq_mode == AcqMode.IntTrigSingle
        kwargs = dict(
            npoints=npoints,
            prepare_once=prepare_once,
            start_once=start_once,
            trigger_type=trigger_type,
            ctrl_params=ctrl_params,
        )
        super().__init__(device, **kwargs)

    def add_counter(self, counter):
        pass

    def __on_event(self, value, signal):
        if signal == StatusSignal:
            self.status = value
            if value == AcqStatus.Ready:
                self._ready_event.set()
        elif signal == PointNbSignal:
            self.last_point_ready = value
            if value >= 0 and not self.use_internal_clock:
                self._ready_event.set()
        elif signal == ErrorSignal:
            self.last_error = value

    def connect(self):
        if self._connected:
            return
        event.connect(self.device, event.Any, self.__on_event)
        self._connected = True

    def disconnect(self):
        if not self._connected:
            return
        event.disconnect(self.device, event.Any, self.__on_event)
        self._connected = False

    def prepare(self):
        self.connect()
        self.first_trigger = True
        device = self.device
        device.acq_mode = self.acq_mode
        device.acq_expo_time = self.acq_expo_time
        device.acq_nb_points = self.npoints
        device.acq_point_period = self.acq_point_period
        self.device.prepare_acq()

    def start(self):
        if (
            self.parent is None
            or self.trigger_type == AcquisitionMaster.HARDWARE  # top master
        ):
            self.trigger()

    def stop(self):
        self.device.stop_acq()
        self.disconnect()

    def trigger(self):
        self._ready_event.clear()
        self.trigger_slaves()

        if self.first_trigger:
            self.first_trigger = False
            self.device.start_acq()
        else:
            self.device.trigger_point()

    def trigger_ready(self):
        return self._ready_event.is_set()

    def wait_ready(self):
        self._ready_event.wait()


class CT2CounterAcquisitionSlave(IntegratingCounterAcquisitionSlave):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__buffer = []
        self.__buffer_event = gevent.event.Event()

    def prepare_device(self):
        channels = []
        counter_indexes = {}
        ctrl = self.device._master_controller
        in_channels = ctrl.INPUT_CHANNELS
        timer_counter = ctrl.internal_timer_counter
        point_nb_counter = ctrl.internal_point_nb_counter
        channel_counters = dict(
            [(counter.channel, counter) for counter in self._counters]
        )
        cntname2channel = {cnt.name: cnt.channel for cnt in self._counters}
        for i, channel in enumerate(sorted(channel_counters)):
            counter = channel_counters[channel]
            if channel in in_channels:
                channels.append(channel)
            elif channel == timer_counter:
                i = -2
                counter.timer_freq = ctrl.timer_freq
            elif channel == point_nb_counter:
                i = -1
            counter_indexes[counter] = i
        ctrl.acq_channels = channels

        def _sort(chan):
            return cntname2channel[chan.short_name]

        self.channels.sort(key=_sort)
        # counter_indexes dict<counter: index in data array>
        def _counters_sort(val):
            k, v = val
            if v >= 0:
                return v
            else:
                return len(counter_indexes) - v + 1

        self.device.counter_indexes = dict(
            sorted(counter_indexes.items(), key=_counters_sort)
        )
        # a hack here: since this prepare is called AFTER the
        # CT2AcquisitionMaster prepare, we do a "second" prepare
        # here after the acq_channels have been configured
        ctrl.prepare_acq()
        self.__buffer = []

    def start_device(self):
        event.connect(self.device._master_controller, DataSignal, self.rx_data)

    def stop_device(self):
        event.disconnect(self.device._master_controller, DataSignal, self.rx_data)
        self.__buffer_event.set()

    def rx_data(self, data, signal):
        self.__buffer.extend(data)
        self.__buffer_event.set()

    def reading(self):
        from_index = 0
        while (
            not self.npoints or self._nb_acq_points < self.npoints
        ) and not self._stop_flag:
            self.__buffer_event.wait()
            self.__buffer_event.clear()
            data = numpy.array(self.__buffer[from_index:], dtype=numpy.uint32)
            if not data.size:
                continue
            data_len = len(data)
            from_index += data_len
            self._nb_acq_points += data_len
            self._emit_new_data(data.T)
        # finally
        data = numpy.array(self.__buffer[from_index:], dtype=numpy.uint32)
        if data.size:
            self._emit_new_data(data.T)

    def _emit_new_data(self, data):
        super()._emit_new_data(
            [c.convert(v) for c, v in zip(self.device.counter_indexes, data)]
        )
