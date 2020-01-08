# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import itertools
from contextlib import closing
from collections import defaultdict

import time
import gevent.event

from bliss.common import event
from bliss.scanning.chain import AcquisitionSlave
from bliss.controllers.mca import TriggerMode, PresetMode

# MCA Acquisition Slave


class McaAcquisitionSlave(AcquisitionSlave):

    READY = "READY"
    TRIGGERED = "TRIGGERED"

    SOFT = TriggerMode.SOFTWARE
    SYNC = TriggerMode.SYNC
    GATE = TriggerMode.GATE

    def __init__(
        self,
        *mca_or_mca_counters,
        npoints=1,
        trigger_mode=SOFT,
        preset_time=1.0,
        block_size=None,
        polling_time=0.1,
        spectrum_size=None,
        prepare_once=True,
        start_once=True,
        ctrl_params=None,
    ):
        # Checks

        # Trigger type
        if isinstance(trigger_mode, str):
            trigger_mode = eval(
                trigger_mode,
                {
                    "TriggerMode": TriggerMode,
                    "SOFTWARE": McaAcquisitionSlave.SOFT,
                    "SYNC": McaAcquisitionSlave.SYNC,
                    "GATE": McaAcquisitionSlave.GATE,
                },
            )
        if trigger_mode == self.SOFT:
            trigger_type = McaAcquisitionSlave.SOFTWARE
        else:
            trigger_type = McaAcquisitionSlave.HARDWARE

        # Parent call
        super().__init__(
            *mca_or_mca_counters,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        # Internals
        self.acquisition_gen = None

        # Default value
        if spectrum_size is None:
            spectrum_size = self.device.spectrum_size

        # Extra arguments
        self.block_size = block_size
        self.preset_time = preset_time
        self.trigger_mode = trigger_mode
        self.polling_time = polling_time
        self.spectrum_size = spectrum_size
        # Reading Queue
        self._pending_datas = gevent.queue.Queue()

        # Add counters

    # Counter management

    def _do_add_counter(self, counter):
        super()._do_add_counter(counter)
        counter.register_device(self)

    # Mode properties

    @property
    def soft_trigger_mode(self):
        return self.trigger_mode == self.SOFT

    @property
    def sync_trigger_mode(self):
        return self.trigger_mode == self.SYNC

    @property
    def gate_trigger_mode(self):
        return self.trigger_mode == self.GATE

    # Standard methods

    def prepare(self):
        """Prepare the acquisition."""
        # Generic configuration
        self.device.trigger_mode = self.trigger_mode
        self.device.spectrum_size = self.spectrum_size
        # Mode-specfic configuration
        if self.soft_trigger_mode:
            self.device.preset_mode = PresetMode.REALTIME
            self.device.preset_value = self.preset_time
        elif self.sync_trigger_mode:
            self.device.hardware_points = self.npoints + 1
            self.device.block_size = self.block_size
        elif self.gate_trigger_mode:
            self.device.hardware_points = self.npoints
            self.device.block_size = self.block_size

        self._pending_datas = gevent.queue.Queue()
        event.connect(self.device, "data", self._data_rx)

    def start(self):
        """Start the acquisition."""
        if self.soft_trigger_mode:
            return
        self.device.start_acquisition()
        if not self.soft_trigger_mode:
            self.device.start_hardware_reading()

    def stop(self):
        """Stop the acquistion."""
        self.device.stop_acquisition()
        event.disconnect(self.device, "data", self._data_rx)
        self._pending_datas.put(StopIteration)
        if not self.soft_trigger_mode:
            self.device.wait_hardware_reading()

    def trigger(self):
        """Send a software trigger."""
        self.device.trigger()

    def reading(self):
        """Spawn by the chain."""
        for nb, values in enumerate(self._pending_datas):
            if isinstance(values, Exception):
                raise values

            spectrums, stats = values
            # Publish
            self._publish(spectrums, stats)
            if self.npoints == nb + 1:
                break

    def _publish(self, spectrums, stats):
        spectrums = self.device._convert_spectrums(spectrums)
        stats = self.device._convert_statistics(stats)
        # Feed data to all counters
        for counter in self._counters:
            point = counter.feed_point(spectrums, stats)
            self.channels.update({f"{self.name}:{counter.name}": point})

    def _data_rx(self, values, signal):
        self._pending_datas.put(values)


# HWSCA Acquisition Slave


class HWScaAcquisitionSlave(AcquisitionSlave):
    def __init__(
        self, mca, npoints=0, prepare_once=True, start_once=True, ctrl_params=None
    ):
        # Parent call
        super().__init__(
            mca,
            npoints=npoints,
            prepare_once=prepare_once,
            start_once=start_once,
            ctrl_params=ctrl_params,
        )

        self.mca = mca
        self.spectrum_size = mca.spectrum_size
        self.scas = list()

    def reading(self):
        pass

    def prepare(self):
        self.mca.set_hardware_scas(self.scas)

    def start(self):
        self.device.start_acquisition()
        self._time_start = time.time()

    def stop(self):
        self.device.stop_acquisition()
        self._time_stop = time.time()

    def trigger(self):
        pass

    def _do_add_counter(self, counter):
        super()._do_add_counter(counter)
        counter.register_device(self)

        (det, start, stop) = (
            counter.detector_channel,
            counter.start_index,
            counter.stop_index,
        )
        self.scas.append(
            (det, min(start, self.spectrum_size - 2), min(stop, self.spectrum_size - 1))
        )
