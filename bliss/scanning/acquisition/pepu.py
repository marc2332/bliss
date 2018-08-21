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

"""\
PePU scan support
=================

The PePU can be integrated in step-by-step scans using the counters
provided by the controller itself::

    # IN channel counters
    >>> pepu.counters.IN1 # to ...
    >>> pepu.counters.IN6

    # CALC channel counters
    >>> pepu.counters.CALC1  # to ...
    >>> pepu.counters.CALC8

    # All channel counters
    >>> list(pepu.counters)

Here's an working example::

    >>> from bliss.config.static import get_config
    >>> from bliss.common.scans import timescan, get_data

    >>> config = get_config()
    >>> pepu = config.get('pepudcm2')

    >>> scan = timescan(1., *pepu.counters, npoints=3)
    [...] # Run the scan for 3 seconds
    >>> data = get_data(scan)
    >>> data['CALC1']
    array([1., 2., 3.])

Note that the values are acquired at the software trigger, not the end of the
integration time.

The PePU is integrated in continuous scans by instanciating the
`PepuAcquisitionDevice` class. It takes the following arguments:

 - `pepu`: the pepu controller
 - `npoints`: the number of points to acquire
 - `start`: the start trigger, default is Signal.SOFT
 - `trigger`: the point trigger, default is Signal.SOFT
 - `frequency`: only used in Signal.FREQ trigger mode
 - `counters`: the PEPU counters to broadcast


Here's an example of a continuous scan using a PePU::

    # Imports
    from bliss.scanning.scan import Scan
    from bliss.controllers.pepu import Signal
    from bliss.config.static import get_config
    from bliss.scanning.chain import AcquisitionChain
    from bliss.scanning.acquisition.motor import MotorMaster
    from bliss.scanning.acquisition.pepu import PepuAcquisitionDevice

    # Get controllers from config
    config = get_config()
    m0 = config.get("roby")
    pepu = config.get("pepudcm2")

    # Instanciate the acquisition device
    device = PepuAcquisitionDevice(pepu, 10, trigger=Signal.DI1)

    # Counters can be added after instanciation
    device.add_counters(pepu.counters)

    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0, npoints=10), device)

    # Run scan
    scan = Scan(chain)
    scan.run()

    # Get the data
    data = scans.get_data(scan)
    print(data['CALC2'])
"""

from ...controllers.pepu import Trigger, Signal
from ..chain import AcquisitionDevice, AcquisitionChannel
from ...common.measurement import BaseCounter, counter_namespace


class PepuAcquisitionDevice(AcquisitionDevice):

    SOFT = Signal.SOFT
    FREQ = Signal.FREQ
    DI1 = Signal.DI1
    DI2 = Signal.DI2

    def __init__(
        self,
        pepu,
        npoints,
        start=Signal.SOFT,
        trigger=Signal.SOFT,
        frequency=None,
        prepare_once=True,
        start_once=True,
        counters=(),
    ):

        # Checking

        assert start_once
        assert prepare_once

        if trigger not in (Signal.SOFT, Signal.FREQ, Signal.DI1, Signal.DI2):
            raise ValueError("{!r} is not a valid trigger".format(trigger))

        if start not in (Signal.SOFT, Signal.DI1, Signal.DI2):
            raise ValueError("{!r} is not a valid start trigger".format(trigger))

        if trigger in (Signal.FREQ,) and frequency is None:
            raise ValueError("Frequency has to be provided for FREQ trigger")

        if trigger in (Signal.FREQ,) and frequency < 1000:
            raise ValueError("Frequency should be greater than or equal to 1000 Hz")

        if trigger not in (Signal.FREQ,) and frequency is not None:
            raise ValueError("Frequency does not make sense without a FREQ trigger")

        trigger_type = self.SOFTWARE if trigger == Signal.SOFT else self.HARDWARE

        # Initialize

        super(PepuAcquisitionDevice, self).__init__(
            pepu,
            pepu.name,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=prepare_once,
            start_once=start_once,
        )

        self.pepu = pepu
        self.stream = None
        self.counters = []
        self.frequency = frequency
        self.add_counters(counters)
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
            self.name,
            trigger=self.trig,
            frequency=self.frequency,
            nb_points=self.npoints,
            sources=sources,
            overwrite=True,
        )
        self.stream.start()
        if self.trig.start == Signal.SOFT and self.trig.clock != Signal.SOFT:
            self.pepu.software_trigger()

    def start(self):
        """Start the acquisition."""
        pass

    def stop(self):
        """Stop the acquisition."""
        if self.stream is not None:
            self.stream.stop()

    def trigger(self):
        """Send a software trigger."""
        if self.trig.clock == Signal.SOFT:
            self.pepu.software_trigger()

    def wait_ready(self):
        """Block until finished."""
        return

    def reading(self):
        """Spawn by the chain."""
        for data in self.stream.idata(self.npoints):
            if len(data):
                self.publish(data)


class PepuCounter(BaseCounter):

    # Default chain integration

    def create_acquisition_device(self, scan_pars, **settings):
        npoints = scan_pars["npoints"]
        return PepuAcquisitionDevice(self.controller, npoints=npoints, **settings)

    def __init__(self, channel):
        self.channel = channel
        self.acquisition_device = None

    # Standard interface

    @property
    def controller(self):
        return self.channel.pepu

    @property
    def name(self):
        return self.channel.name

    @property
    def dtype(self):
        return float

    @property
    def shape(self):
        return ()

    # Extra logic

    def register_device(self, device):
        assert device.pepu == self.channel.pepu
        self.acquisition_device = device
        self.acquisition_device.channels.append(
            AcquisitionChannel(self.name, self.dtype, self.shape)
        )

    def feed_point(self, stream_data):
        self.emit_data_point(stream_data[self.name])

    def emit_data_point(self, data_point):
        self.acquisition_device.channels.update({self.name: data_point})


def pepu_counters(pepu):
    """Provide a convenient access to the PEPU counters."""
    channels = pepu.in_channels.values() + pepu.calc_channels.values()
    counters = map(PepuCounter, channels)
    return counter_namespace(counters)
