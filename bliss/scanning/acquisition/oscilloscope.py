# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.scanning.acquisition.counter import BaseCounterAcquisitionSlave
from bliss.scanning.chain import AcquisitionSlave
from bliss.scanning.channel import AcquisitionChannel
import gevent
import numpy

from collections import namedtuple

OscAnalogChanData = namedtuple("OscAnalogChanData", "length raw_data data header")
OscMeasData = namedtuple("OscMeasData", "value header")


class OscilloscopeAcquisitionSlave(BaseCounterAcquisitionSlave):
    def __init__(
        self,
        *counters,
        count_time,
        npoints=1,
        trigger_type=AcquisitionSlave.SOFTWARE,
        ctrl_params=None,
    ):
        BaseCounterAcquisitionSlave.__init__(
            self,
            *counters,
            count_time=count_time,
            npoints=npoints,
            trigger_type=trigger_type,
            ctrl_params=ctrl_params,
            prepare_once=False,
            start_once=False,
        )

    def _do_add_counter(self, counter):
        from bliss.controllers.oscilloscope import OscilloscopeAnalogChannel

        super()._do_add_counter(counter)  # add the 'default' counter

        # add additional channel for raw data
        if isinstance(counter, OscilloscopeAnalogChannel):
            self.channels.append(
                AcquisitionChannel(
                    f"{counter.fullname}_raw", counter.dtype, counter.shape, unit=None
                )
            )
            self._counters[counter].append(self.channels[-1])

    def prepare(self):
        self.device._scope._device.acq_prepare()

    def start(self):
        self.device._scope._device.acq_start()

    #   def trigger(self):
    #       print("trigger")

    def stop(self):
        # read final header to publish ... or do that in the correspoinding function...
        pass

    def reading(self):
        data = [numpy.nan] * len(self.channels)  # is this really needed?
        from bliss.controllers.oscilloscope import (
            OscilloscopeAnalogChannel,
            OscilloscopeMeasurement,
        )

        # check if busy like mca

        try:
            with gevent.timeout.Timeout(self.count_time):
                while not self.device._scope._device.acq_done():
                    gevent.sleep(self.count_time / 5.0)
        except TimeoutError:
            raise TimeoutError("scope did not finish aquisition within count time")

        self.device._scope._device.wait_ready()

        # get data
        for counter, channels in self._counters.items():
            if isinstance(counter, OscilloscopeAnalogChannel):
                reading = self.device._scope._device.acq_read_channel(counter.name)
                data[
                    self.channels.index(channels[0])
                ] = reading.data  # is there no simpler way to to this?
                data[self.channels.index(channels[1])] = reading.raw_data

                # maybe there is a smarter place to deal with shape
                if channels[0].shape == (1,):
                    channels[0].shape = reading.data.shape
                    channels[1].shape = reading.data.shape

            if isinstance(counter, OscilloscopeMeasurement):
                reading = self.device._scope._device.acq_read_measurement(counter.name)
                data[self.channels.index(channels[0])] = reading.value

        # publish data
        self._emit_new_data(data)

    # ...
    # self._emit_new_data(data)

    """
    In order to guarantee that the waveform data returned from CURVE?
queries of multiple waveforms are correlated to the same acquisition, you should
use single sequence acquisition mode to acquire the waveform data from a single
acquisition. Single sequence acquisition mode is enabled using SEQuence.
    """
