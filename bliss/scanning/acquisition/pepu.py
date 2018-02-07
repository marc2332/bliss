# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import namedtuple

from ..chain import AcquisitionDevice, AcquisitionChannel
from ...controllers.pepu import Trigger, Signal


class PepuAcquisitionDevice(AcquisitionDevice):

    SOFT = Signal.SOFT
    FREQ = Signal.FREQ
    DI1 = Signal.DI1
    DI2 = Signal.DI2

    def __init__(self, pepu, npoints,
                 start=Signal.SOFT, trigger=Signal.SOFT,
                 frequency=None,
                 prepare_once=True, start_once=True,
                 counters=()):

        # Checking

        assert start_once
        assert prepare_once

        if trigger not in (Signal.SOFT, Signal.FREQ, Signal.DI1, Signal.DI2):
            raise ValueError(
                '{!r} is not a valid trigger'.format(trigger))

        if start not in (Signal.SOFT, Signal.DI1, Signal.DI2):
            raise ValueError(
                '{!r} is not a valid start trigger'.format(trigger))

        if trigger in (Signal.FREQ,) and frequency is None:
            raise ValueError(
                'Frequency has to be provided for FREQ trigger')

        if trigger in (Signal.FREQ,) and frequency < 1000:
            raise ValueError(
                'Frequency should be greater than or equal to 1000 Hz')

        if trigger not in (Signal.FREQ,) and frequency is not None:
            raise ValueError(
                'Frequency does not make sense without a FREQ trigger')

        trigger_type = \
            self.SOFTWARE if trigger == Signal.SOFT else self.HARDWARE

        # Initialize

        super(PepuAcquisitionDevice, self).__init__(
            pepu, pepu.name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once)

        self.pepu = pepu
        self.stream = None
        self.frequency = frequency
        self.counters = list(counters)
        self.trig = Trigger(start, trigger)

    # Counter management

    def add_counter(self, counter):
        self.counters.append(counter)
        counter.register_device(self)

    def add_counters(self, counters):
        for counter in counters:
            self.add_counter(counter)

    def publish(self, data):
        for counter in self.counters:
            counter.feed_point(data)

    # Standard methods

    def prepare(self):
        """Prepare the acquisition."""
        sources = [counter.name for counter in self.counters]
        self.stream = self.pepu.create_stream(
            self.name, trigger=self.trig, frequency=self.frequency,
            nb_points=self.npoints, sources=sources, overwrite=True)

    def start(self):
        """Start the acquisition."""
        self.stream.start()

    def stop(self):
        """Stop the acquisition."""
        self.stream.stop()

    def trigger(self):
        """Send a software trigger."""
        if self.trig.start == Signal.SOFT:
            self.pepu.software_trigger()

    def wait_ready(self):
        """Block until finished."""
        return

    def reading(self):
        """Spawn by the chain."""
        for data in self.stream.idata():
            if data:
                self.publish(data)


class PepuCounter(object):

    def __init__(self, channel):
        self.channel = channel
        self.acquisition_controller = None

    @property
    def name(self):
        return self.channel.name

    @property
    def dtype(self):
        return float

    @property
    def shape(self):
        return ()

    def register_device(self, device):
        assert device.pepu == self.channel.pepu
        self.acquisition_controller = device
        self.acquisition_controller.channels.append(
            AcquisitionChannel(self.name, self.dtype, self.shape))

    def feed_point(self, stream_data):
        self.emit_data_point(stream_data[self.name])

    def emit_data_point(self, data_point):
        self.acquisition_controller.channels.update({self.name: data_point})


def pepu_counters(pepu):
    """Provide a convenient access to the PEPU counters."""
    channels = pepu.in_channels.values() + pepu.calc_channels.values()
    counters = map(PepuCounter, channels)
    names = (channel.name for channel in channels)
    return namedtuple('PepuCounters', names)(*counters)
