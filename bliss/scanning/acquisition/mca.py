# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import defaultdict

import numpy
import gevent.event

from ..chain import AcquisitionDevice, AcquisitionChannel
from ...controllers.mca import TriggerMode, PresetMode


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


class McaAcquisitionDevice(AcquisitionDevice):

    READY = 'READY'
    TRIGGERED = 'TRIGGERED'
    ACQUIRING = 'ACQUIRING'

    SOFT = TriggerMode.SOFTWARE
    SYNC = TriggerMode.SYNC
    GATE = TriggerMode.GATE

    def __init__(self, mca, npoints, trigger_mode=SOFT,
                 preset_time=1., block_size=None, polling_time=0.1,
                 spectrum_size=None, prepare_once=True, start_once=True):
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

        # Channels
        metadata = [
            ('spectrum', numpy.uint32, (self.spectrum_size,)),
            ('realtime', numpy.float,  ()),
            ('livetime', numpy.float,  ()),
            ('triggers', numpy.int,    ()),
            ('events',   numpy.int,    ()),
            ('icr',      numpy.float,  ()),
            ('ocr',      numpy.float,  ()),
            ('deadtime', numpy.float,  ())]
        for n in mca.elements:
            prefix = 'det{}_'.format(n)
            for name, dtype, shape in metadata:
                self.channels.append(
                    AcquisitionChannel(prefix + name, dtype, shape))

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
        # Generic configuration
        self.device.set_trigger_mode(self.trigger_mode)
        self.device.set_spectrum_size(self.spectrum_size)
        # Mode-specfic configuration
        if self.soft_trigger_mode:
            self.device.set_preset_mode(PresetMode.REALTIME, self.preset_time)
        elif self.sync_trigger_mode:
            self.device.set_hardware_points(self.npoints + 1)
            self.set_block_size(self.block_size)
        elif self.gate_trigger_mode:
            self.device.set_hardware_points(self.npoints)
            self.set_block_size(self.block_size)

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
            self.acquisition_state.move(self.TRIGGERED, self.ACQUIRING)
            # Get data
            spectrums, stats = next(self.acquisition_gen)
            # Publish
            self._publish(spectrums, stats)
            # Software sync
            self.acquisition_state.goto(self.READY)

    def _publish(self, data, stats):
        data_dict = {}
        # Loop over detectors
        for n, spectrum in data.items():
            stat = stats[n]
            prefix = 'det{}_'.format(n)
            # Update data dict
            data_dict[prefix + 'spectrum'] = spectrum
            for name, value in stat._asdict().items():
                data_dict[prefix + name] = value
        # Emit data
        self.channels.update(data_dict)
