# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PEPU Acquisition Device.
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
        npoints=1,
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

        super().__init__(
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

    def publish(self, data):
        for counter in self._counters:
            self.channels.update(
                {f"{self.device.name}:{counter.name}": data[counter.name]}
            )

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
            if len(data) > 0:
                self.publish(data)
