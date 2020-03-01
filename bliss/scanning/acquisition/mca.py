# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import itertools
from contextlib import closing
from collections import defaultdict

import time
import gevent.event


from bliss.scanning.chain import AcquisitionSlave
from bliss.controllers.mca import TriggerMode, PresetMode


class StateMachine(object):
    def __init__(self, state):
        self._state = state
        self._state_dict = defaultdict(gevent.event.Event)
        self._state_dict[state].set()

    @property
    def state(self):
        return self._state

    def wait(self, state):
        self._state_dict[state].wait()

    def goto(self, state):
        self._state_dict[self._state].clear()
        self._state = state
        self._state_dict[state].set()

    def move(self, source, destination):
        self.wait(source)
        self.goto(destination)


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
        self.acquisition_state = StateMachine(self.READY)

        # Default value
        if spectrum_size is None:
            spectrum_size = self.device.spectrum_size

        # Extra arguments
        self.block_size = block_size
        self.preset_time = preset_time
        self.trigger_mode = trigger_mode
        self.polling_time = polling_time
        self.spectrum_size = spectrum_size

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

    def start(self):
        """Start the acquisition."""
        if self.soft_trigger_mode:
            return
        self.device.start_acquisition()

    def stop(self):
        """Stop the acquistion."""
        if self.soft_trigger_mode:
            self._reading_task.kill()
        else:
            self.device.stop_acquisition()
        self.acquisition_state.goto(self.READY)

    def trigger(self):
        """Send a software trigger."""
        self.acquisition_state.move(self.READY, self.TRIGGERED)

    def trigger_ready(self):
        if self.soft_trigger_mode:
            return self.acquisition_state.state == self.READY
        return True

    def wait_ready(self):
        """Block until finished."""
        if self.soft_trigger_mode:
            self.acquisition_state.wait(self.READY)

    def reading(self):
        """Spawn by the chain."""
        # Buffer for the data to publish
        try:
            publishing_dict = defaultdict(list)

            # Spawn the real reading task
            task = gevent.spawn(
                self._soft_reading if self.soft_trigger_mode else self._hard_reading,
                publishing_dict,
            )

            # Periodically publish
            while True:

                # Use task.get as a conditional sleep
                try:
                    task.get(timeout=self.polling_time)

                # Tick
                except gevent.Timeout:
                    pass

                # The reading task has terminated
                else:
                    break

                # Publish all items from publishing_dict
                finally:
                    # ensure no greenlet switch will alter publishing_dict,
                    # we update channels with a copy and so we can clear
                    # the dict just after to continue putting values in it
                    # from data acquisition task
                    publishing_dict_copy = publishing_dict.copy()
                    publishing_dict.clear()
                    self.channels.update(publishing_dict_copy)
                    del publishing_dict_copy

        # Make sure the reading task has completed
        finally:
            task.kill()

    # Helpers

    def _hard_reading(self, publishing_dict):
        npoints = self.npoints + 1 if self.sync_trigger_mode else self.npoints

        # Safe point generator
        with closing(
            self.device.hardware_poll_points(npoints, self.polling_time)
        ) as generator:

            # Discard first point in synchronized mode
            if self.sync_trigger_mode:
                next(generator)

            # Acquire data
            for spectrums, stats in generator:
                self._publish(publishing_dict, spectrums, stats)

    def _soft_reading(self, publishing_dict):

        # Safe point generator
        with closing(
            self.device.software_controlled_run(self.npoints, self.polling_time)
        ) as generator:

            # Acquire data
            indexes = (
                itertools.count() if self.npoints == 0 else list(range(self.npoints))
            )
            for i in indexes:

                # Software sync
                self.acquisition_state.wait(self.TRIGGERED)

                # Get data
                spectrums, stats = next(generator)

                # Publish
                self._publish(publishing_dict, spectrums, stats)

                # Software sync
                self.acquisition_state.goto(self.READY)

    def _publish(self, publishing_dict, spectrums, stats):
        # Feed data to all counters
        for counter in self._counters:
            point = counter.feed_point(spectrums, stats)

            # Atomic - add point to publising dict
            publishing_dict[counter.fullname].append(point)


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
