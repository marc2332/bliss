# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import itertools
from contextlib import closing
from collections import defaultdict

import numpy
import gevent.event

from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.controllers.mca import TriggerMode, PresetMode, Stats
from bliss.common.measurement import BaseCounter, counter_namespace, namespace


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


# Acquisition device


class McaAcquisitionDevice(AcquisitionDevice):

    READY = "READY"
    TRIGGERED = "TRIGGERED"

    SOFT = TriggerMode.SOFTWARE
    SYNC = TriggerMode.SYNC
    GATE = TriggerMode.GATE

    def __init__(
        self,
        mca,
        npoints,
        trigger_mode=SOFT,
        preset_time=1.0,
        block_size=None,
        polling_time=0.1,
        spectrum_size=None,
        counters=(),
        prepare_once=True,
        start_once=True,
    ):
        # Checks
        assert start_once
        assert prepare_once

        # Trigger type
        if isinstance(trigger_mode, str):
            trigger_mode = eval(
                trigger_mode,
                {
                    "TriggerMode": TriggerMode,
                    "SOFTWARE": McaAcquisitionDevice.SOFT,
                    "SYNC": McaAcquisitionDevice.SYNC,
                    "GATE": McaAcquisitionDevice.GATE,
                },
            )
        if trigger_mode == self.SOFT:
            trigger_type = McaAcquisitionDevice.SOFTWARE
        else:
            trigger_type = McaAcquisitionDevice.HARDWARE

        # Parent call
        super(McaAcquisitionDevice, self).__init__(
            mca,
            mca.name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
        )

        # Internals
        self.mca = mca
        self.counters = []
        self.acquisition_gen = None
        self.acquisition_state = StateMachine(self.READY)

        # Default value
        if spectrum_size is None:
            spectrum_size = mca.spectrum_size

        # Extra arguments
        self.block_size = block_size
        self.preset_time = preset_time
        self.trigger_mode = trigger_mode
        self.polling_time = polling_time
        self.spectrum_size = spectrum_size

        # Add counters
        self.add_counters(counters)

    # Counter management

    def add_counter(self, counter):
        self.counters.append(counter)
        counter.register_device(self)

    def add_counters(self, counters):
        for counter in counters:
            self.add_counter(counter)

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
        self.device.set_trigger_mode(self.trigger_mode)
        self.device.set_spectrum_size(self.spectrum_size)
        # Mode-specfic configuration
        if self.soft_trigger_mode:
            self.device.set_preset_mode(PresetMode.REALTIME, self.preset_time)
        elif self.sync_trigger_mode:
            self.device.set_hardware_points(self.npoints + 1)
            self.device.set_block_size(self.block_size)
        elif self.gate_trigger_mode:
            self.device.set_hardware_points(self.npoints)
            self.device.set_block_size(self.block_size)

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

                # Pop and publish all items from publishing_dict
                finally:
                    while publishing_dict:

                        # Atomic - pop the points of a single counter
                        name, points = publishing_dict.popitem()

                        # Actual publishing
                        self.channels.update({name: points})

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
        for counter in self.counters:
            point = counter.feed_point(spectrums, stats)

            # Atomic - add point to publising dict
            publishing_dict[counter.name].append(point)


# Mca counters


class BaseMcaCounter(BaseCounter):

    # Default chain integration

    def create_acquisition_device(
        self, scan_pars, device_dict=None, master_dict=None, **settings
    ):
        npoints = scan_pars["npoints"]
        count_time = scan_pars["count_time"]

        return McaAcquisitionDevice(
            self.controller, npoints=npoints, preset_time=count_time, **settings
        )

    def __init__(self, mca, base_name, detector=None):
        self.mca = mca
        self.acquisition_device = None
        self.data_points = []
        self.detector_channel = detector
        self.base_name = base_name

    # Standard counter interface

    @property
    def controller(self):
        return self.mca

    @property
    def name(self):
        if self.detector_channel is None:
            return self.base_name
        return "{}_det{}".format(self.base_name, self.detector_channel)

    @property
    def dtype(self):
        return numpy.float

    @property
    def shape(self):
        return ()

    # Extra logic

    def register_device(self, device):
        # Current device
        self.data_points = []
        self.acquisition_device = device
        # Consistency checks
        assert self.controller is self.acquisition_device.mca
        if self.detector_channel is not None:
            assert self.detector_channel in self.controller.elements
        # Acquisition channel
        self.acquisition_device.channels.append(
            AcquisitionChannel(self, self.name, self.dtype, self.shape)
        )

    def extract_point(self, spectrums, stats):
        raise NotImplementedError

    def feed_point(self, spectrums, stats):
        point = self.extract_point(spectrums, stats)
        self.data_points.append(point)
        return point


class StatisticsMcaCounter(BaseMcaCounter):
    def __init__(self, mca, stat_name, detector):
        self.stat_name = stat_name
        assert stat_name in Stats._fields
        super(StatisticsMcaCounter, self).__init__(mca, stat_name, detector)

    @property
    def dtype(self):
        if self.stat_name in ("triggers", "events"):
            return numpy.int
        return numpy.float

    def extract_point(self, spectrums, stats):
        return getattr(stats[self.detector_channel], self.stat_name)


class SpectrumMcaCounter(BaseMcaCounter):
    def __init__(self, mca, detector):
        super(SpectrumMcaCounter, self).__init__(mca, "spectrum", detector)

    @property
    def dtype(self):
        return numpy.uint32

    @property
    def shape(self):
        if self.acquisition_device is None:
            return (self.controller.spectrum_size,)
        return (self.acquisition_device.spectrum_size,)

    def extract_point(self, spectrums, stats):
        return spectrums[self.detector_channel]


class RoiMcaCounter(BaseMcaCounter):
    def __init__(self, mca, roi_name, detector):
        self.roi_name = roi_name
        self.start_index, self.stop_index = None, None
        super(RoiMcaCounter, self).__init__(mca, roi_name, detector)

    def register_device(self, device):
        super(RoiMcaCounter, self).register_device(device)
        self.start_index, self.stop_index = self.mca.rois.resolve(self.roi_name)

    @property
    def dtype(self):
        return numpy.int

    def compute_roi(self, spectrum):
        return sum(spectrum[self.start_index : self.stop_index])

    def extract_point(self, spectrums, stats):
        return self.compute_roi(spectrums[self.detector_channel])


class RoiSumMcaCounter(RoiMcaCounter):
    def __init__(self, mca, roi_name):
        super(RoiSumMcaCounter, self).__init__(mca, roi_name, None)

    def extract_point(self, spectrums, stats):
        return sum(map(self.compute_roi, spectrums.values()))


def mca_counters(mca):
    """Provide a flat access to all MCA counters.

    - counters.spectrum_det<N>
    - counters.realtime_det<N>
    - counters.livetime_det<N>
    - counters.triggers_det<N>
    - counters.events_det<N>
    - counters.icr_det<N>
    - counters.ocr_det<N>
    - counters.deadtime_det<N>
    """
    # Spectrum
    counters = [SpectrumMcaCounter(mca, element) for element in mca.elements]
    # Stats
    counters += [
        StatisticsMcaCounter(mca, stat, element)
        for element in mca.elements
        for stat in Stats._fields
    ]
    # Rois
    counters += [
        RoiMcaCounter(mca, roi, element)
        for element in mca.elements
        for roi in mca.rois.get_names()
    ]

    # Roi sums
    counters += [RoiSumMcaCounter(mca, roi) for roi in mca.rois.get_names()]

    # Instantiate
    return counter_namespace(counters)


def mca_counter_groups(mca):
    """Provide a group access to MCA counters.

    - groups.spectrum
    - groups.realtime
    - groups.livetime
    - groups.triggers
    - groups.events
    - groups.icr
    - groups.ocr
    - groups.deadtime
    - groups.det<N>
    """
    dct = {}
    counters = mca_counters(mca)
    roi_names = list(mca.rois.get_names())

    # Prefix groups
    prefixes = list(Stats._fields) + ["spectrum"] + roi_names
    for prefix in prefixes:
        dct[prefix] = counter_namespace(
            [counter for counter in counters if counter.name.startswith(prefix)]
        )

    # Suffix groups
    suffixes = ["det{}".format(e) for e in mca.elements]
    for suffix in suffixes:
        dct[suffix] = counter_namespace(
            [counter for counter in counters if counter.name.endswith(suffix)]
        )

    # Instantiate group namespace
    return namespace(dct)
