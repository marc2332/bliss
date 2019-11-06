# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
    >>> from bliss.common.scans import timescan
    >>> from bliss.data.scan import get_data

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
`PepuAcquisitionSlave` class. It takes the following arguments:

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
    from bliss.scanning.acquisition.pepu import PepuAcquisitionSlave

    # Get controllers from config
    config = get_config()
    m0 = config.get("roby")
    pepu = config.get("pepudcm2")

    # Instanciate the acquisition device
    device = PepuAcquisitionSlave(pepu, 10, trigger=Signal.DI1)

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

from bliss.controllers.pepu import Trigger, Signal
from bliss.scanning.chain import AcquisitionSlave


class PepuAcquisitionSlave(AcquisitionSlave):

    SOFT = Signal.SOFT
    FREQ = Signal.FREQ
    DI1 = Signal.DI1
    DI2 = Signal.DI2

    def __init__(
        self,
        *pepu_or_pepu_counters,
        npoints,
        start=Signal.SOFT,
        trigger=Signal.SOFT,
        frequency=None,
        ctrl_params=None,
    ):

        # Checking

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

        super(PepuAcquisitionSlave, self).__init__(
            *pepu_or_pepu_counters,
            npoints=npoints,
            trigger_type=trigger_type,
            prepare_once=True,
            start_once=True,
            ctrl_params=ctrl_params,
        )

        self.stream = None
        self.frequency = frequency
        self.trig = Trigger(start, trigger)

    # Counter management

    def _do_add_counter(self, counter):
        assert self.device == counter.channel.pepu
        super()._do_add_counter(counter)
        counter.acquisition_device = self

    def publish(self, data):
        for counter in self._counters:
            counter.feed_point(data)

    # Standard methods

    def prepare(self):
        """Prepare the acquisition."""
        sources = [counter.name for counter in self._counters]
        self.stream = self.device.create_stream(
            self.name,
            trigger=self.trig,
            frequency=self.frequency,
            nb_points=self.npoints,
            sources=sources,
            overwrite=True,
        )
        self.stream.start()
        if self.trig.start == Signal.SOFT and self.trig.clock != Signal.SOFT:
            self.device.software_trigger()

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
            self.device.software_trigger()

    def reading(self):
        """Spawn by the chain."""
        for data in self.stream.idata(self.npoints):
            if len(data):
                self.publish(data)
