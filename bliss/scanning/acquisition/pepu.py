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
from ...controllers.pepu import Trigger, Signal, StreamInfo


class PEPUAcquisitionDevice(AcquisitionDevice):

    def __init__(self, pepu, npoints, frequency=1000,
                 start=Signal.SOFT, trigger=Signal.FREQ,
                 prepare_once=True, start_once=True,
                 counters=()):
        assert start_once
        assert prepare_once
        if trigger == Signal.SOFT:
            trigger_type = self.SOFTWARE
        else:
            trigger_type = self.HARDWARE

        super(PEPUAcquisitionDevice, self).__init__(
            pepu, pepu.name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once)

        self.pepu = pepu
        self.frequency = frequency
        self.trig = Trigger(start, trigger)
        self.counters = list(counters)

    def prepare(self):
        sources = [counter.name for counter in self.counters]
        self.stream = self.pepu.create_stream(self.name,
                                              trigger=self.trig,
                                              frequency=self.frequency,
                                              nb_points=self.npoints,
                                              sources=sources,
                                              overwrite=True)

    def start(self):
        self.stream.start()
        if self.trig.start == Signal.SOFT:
            self.pepu.software_trigger()

    def stop(self):
        self.stream.stop()

    def trigger(self):
        """Send a software trigger."""
        print 'trigger'

    def reading(self):
        """Spawn by the chain."""
        return self.stream.read()


class PEPUCounter(object):

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
        return (self.acquisition_controller.nsamples,)

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
    counters = map(PEPUCounter, channels)
    names = (channel.name for channel in channels)
    return namedtuple('PEPUCounters', names)(*counters)
