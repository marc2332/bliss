# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""CT2 (P201/C208) bliss acquisition master"""

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
        # counter_indexes dict<counter: index in data array>
        self.device.counter_indexes = counter_indexes
        # a hack here: since this prepare is called AFTER the
        # CT2AcquisitionMaster prepare, we do a "second" prepare
        # here after the acq_channels have been configured
        ctrl.prepare_acq()
