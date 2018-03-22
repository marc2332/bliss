# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import defaultdict, namedtuple

import numpy
import gevent.event

from ..chain import AcquisitionDevice, AcquisitionChannel
from ...controllers.mca import TriggerMode, PresetMode, Stats


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

    READY = 'READY'
    TRIGGERED = 'TRIGGERED'

    SOFT = TriggerMode.SOFTWARE
    SYNC = TriggerMode.SYNC
    GATE = TriggerMode.GATE

    def __init__(self, mca, npoints, trigger_mode=SOFT,
                 preset_time=1., block_size=None, polling_time=0.1,
                 spectrum_size=None, counters=(),
                 prepare_once=True, start_once=True):
        # Checks
        assert start_once
        assert prepare_once

        # Trigger type
        if trigger_mode == self.SOFT:
            trigger_type = McaAcquisitionDevice.SOFTWARE
        else:
            trigger_type = McaAcquisitionDevice.HARDWARE

        # Parent call
        super(McaAcquisitionDevice, self).__init__(
            mca, mca.name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=True,
            start_once=True)

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
        for counter in counters:
            self.add_counter(counter)

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
            self.acquisition_gen = self.device.software_controlled_run(
                self.npoints, self.polling_time)
        elif self.sync_trigger_mode:
            self.acquisition_gen = self.device.hardware_controlled_run(
                self.npoints + 1, self.polling_time)
        elif self.gate_trigger_mode:
            self.acquisition_gen = self.device.hardware_controlled_run(
                self.npoints, self.polling_time)

    def stop(self):
        """Stop the acquistion."""
        if self.acquisition_gen:
            self.acquisition_gen.close()
        self.acquisition_state.goto(self.READY)

    def trigger(self):
        """Send a software trigger."""
        self.acquisition_state.move(self.READY, self.TRIGGERED)

    def wait_ready(self):
        """Block until finished."""
        if self.soft_trigger_mode:
            self.acquisition_state.wait(self.READY)

    def reading(self):
        """Spawn by the chain."""
        if self.soft_trigger_mode:
            return self._soft_reading()
        return self._hard_reading()

    # Helpers

    def _hard_reading(self):
        # Discard first acquisition in synchronized mode
        if self.sync_trigger_mode:
            next(self.acquisition_gen)
        # Acquire data
        for spectrums, stats in self.acquisition_gen:
            # Publish
            self._publish(spectrums, stats)

    def _soft_reading(self):
        # Acquire data
        for i in range(self.npoints):
            # Software sync
            self.acquisition_state.wait(self.TRIGGERED)
            # Get data
            spectrums, stats = next(self.acquisition_gen)
            # Publish
            self._publish(spectrums, stats)
            # Software sync
            self.acquisition_state.goto(self.READY)

    def _publish(self, spectrums, stats):
        for counter in self.counters:
            counter.feed_point(spectrums, stats)


# Default chain plugin

def mca_default_chain_plugin(tree, counters, scan_pars):
    mca_counters = {}
    npoints = scan_pars['npoints']
    count_time = scan_pars['count_time']
    # Group counters by controller
    for counter in counters:
        if isinstance(counter, BaseMcaCounter):
            mca_counters.setdefault(counter.controller, []).append(counter)
    # Remove mca counters from the counter set
    for counter_list in mca_counters.values():
        counters -= set(counter_list)
    # Create acquistion devices
    for mca, counter_list in mca_counters.items():
        acq_device = McaAcquisitionDevice(
            mca, npoints=npoints, preset_time=count_time,
            counters=counter_list)
        tree.setdefault(None, []).append(acq_device)
    # Return altered counter set
    return counters


# Mca counters

class BaseMcaCounter(object):

    default_chain_plugin = staticmethod(mca_default_chain_plugin)

    def __init__(self, mca, base_name, detector=None):
        self.controller = mca
        self.acquisition_controller = None
        self.data_points = []
        self.detector_channel = detector
        self.base_name = base_name

    @property
    def name(self):
        if self.detector_channel is None:
            return self.base_name
        return '{}_det{}'.format(self.base_name, self.detector_channel)

    @property
    def dtype(self):
        return numpy.float

    @property
    def shape(self):
        return ()

    def register_device(self, device):
        # Current device
        self.data_points = []
        self.acquisition_controller = device
        # Consistency checks
        assert self.controller is self.acquisition_controller.mca
        if self.detector_channel is not None:
            assert self.detector_channel in self.controller.elements
        # Acquisition channel
        self.acquisition_controller.channels.append(
            AcquisitionChannel(self.name, self.dtype, self.shape))

    def feed_point(self, spectrums, stats):
        raise NotImplementedError

    def emit_data_point(self, data_point):
        self.acquisition_controller.channels.update({self.name: data_point})
        self.data_points.append(data_point)


class StatisticsMcaCounter(BaseMcaCounter):

    def __init__(self, mca, stat_name, detector):
        self.stat_name = stat_name
        assert stat_name in Stats._fields
        super(StatisticsMcaCounter, self).__init__(
            mca, stat_name, detector)

    @property
    def dtype(self):
        if self.stat_name in ('triggers', 'events'):
            return numpy.int
        return numpy.float

    def feed_point(self, spectrums, stats):
        point = getattr(stats[self.detector_channel], self.stat_name)
        self.emit_data_point(point)


class SpectrumMcaCounter(BaseMcaCounter):

    def __init__(self, mca, detector):
        super(SpectrumMcaCounter, self).__init__(
            mca, 'spectrum', detector)

    @property
    def dtype(self):
        return numpy.uint32

    @property
    def shape(self):
        if self.acquisition_controller is None:
            return (self.controller.spectrum_size,)
        return (self.acquisition_controller.spectrum_size,)

    def feed_point(self, spectrums, stats):
        self.emit_data_point(spectrums[self.detector_channel])


def counter_namespace(name, counters):
    dct = {counter.name: counter for counter in counters}
    cls = namedtuple(name, sorted(dct))
    return cls(**dct)


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
    counters = [SpectrumMcaCounter(mca, element)
                for element in mca.elements]
    # Stats
    counters += [StatisticsMcaCounter(mca, stat, element)
                 for element in mca.elements
                 for stat in Stats._fields]
    # Instantiate
    return counter_namespace('McaCounters', counters)


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

    # Prefix groups
    prefixes = list(Stats._fields) + ['spectrum']
    for prefix in prefixes:
        dct[prefix] = counter_namespace(
            counter for counter in counters
            if counter.name.startswith(prefix))

    # Suffix groups
    suffixes = ['det{}'.format(e) for e in mca.elements]
    for suffix in suffixes:
        dct[suffix] = counter_namespace(
            counter for counter in counters
            if counter.name.startswith(prefix))

    # Instantiate group namespace
    cls = namedtuple('McaGroups', sorted(dct))
    return cls(**dct)
