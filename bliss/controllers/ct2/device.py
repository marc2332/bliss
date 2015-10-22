# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright (c) : 2015
# Beamline Control Unit, European Synchrotron Radiation Facility
# BP 220, Grenoble 38043
# FRANCE
#
# Distributed under the terms of the GNU Lesser General Public License,
# either version 3 of the License, or (at your option) any later version.
# See LICENSE.txt for more info.

import numpy
from gevent import select
from louie import dispatcher

try:
    import enum
except:
    from . import enum34 as enum

from . import ct2


ErrorSignal = "error"
StopSignal = "stop"
PointNbSignal = "point_nb"


class AcqMode(enum.Enum):

    Internal = 0


class BaseCT2Device(object):

    internal_timer_counter = 11
    internal_point_nb_counter = 12

    def __init__(self, config, name):
        self.__config = config
        self.__name = name

    # helper methods to fire events

    def _send_error(self, error):
        dispatcher.send(ErrorSignal, self, error)

    def _send_point_nb(self, point_nb):
        dispatcher.send(PointNbSignal, self, point_nb)

    def _send_stop(self):
        dispatcher.send(StopSignal, self)

    @property
    def config(self):
        return self.__config

    @property
    def card_config(self):
        return self.config.get_config(self.__name)

    @property
    def name(self):
        return self.__name

    @property
    def _device(self):
        raise NotImplementedError

    @property
    def use_mmap(self):
        return self._device.use_mmap

    @use_mmap.setter
    def use_mmap(self, use_mmap):
        self._device.use_mmap = use_mmap
    
    @property
    def acq_mode(self):
        return self._device.acq_mode

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self._device.acq_mode = acq_mode

    @property
    def acq_nb_points(self):
        return self._device.acq_nb_points

    @acq_nb_points.setter
    def acq_nb_points(self, acq_nb_points):
        self._device.acq_nb_points = acq_nb_points

    @property
    def acq_expo_time(self):
        return self._device.acq_expo_time

    @acq_expo_time.setter
    def acq_expo_time(self, acq_expo_time):
        self._device.acq_expo_time = acq_expo_time

    @property
    def acq_channels(self):
        return self._device.acq_channels

    @acq_channels.setter
    def acq_channels(self, acq_channels):
        self._device.acq_channels = acq_channels

    def reset(self):
        self._device.reset()

    def prepare_acq(self):
        self._device.prepare_acq()

    def start_acq(self):
        self._device.start_acq()

    def apply_config():
        self._device.apply_config()

    def read_data(self):
        self._device.read_data(use_mmap)

    @property
    def counters(self):
        return self._device.counters

    @property
    def latches(self):
        return self._device.latches


class CT2Device(BaseCT2Device):
    """
    Helper for a locally installed CT2 card (P201/C208).
    """

    def __init__(self, config, name):
        BaseCT2Device.__init__(self, config, name)
        self.__buffer = []
        self.__card = self.config.get(self.name)
        self.__acq_mode = AcqMode.Internal
        self.__acq_expo_time = 1.0
        self.__acq_nb_points = 1
        self.__acq_channels = ()

    def run_forever(self):
        card = self.__card

        while True:
            read, write, error = select.select((card,), (), (card,))
            try:
                if error:
                    self._send_error("ct2 select error on {0}".format(error))
                if read:
                    (counters, channels, dma, fifo_half_full, err), tstamp = \
                        card.acknowledge_interrupt()
                    if err:
                        self._send_error("ct2 error")
                    if dma:
                        data, fifo_status = card.read_fifo()
                        self.__buffer.append(data)
                        point_nb = data[-1][-1]
                        self._send_point_nb(point_nb)
                    if self.__acq_mode == AcqMode.Internal:
                        if self.internal_point_nb_counter in counters:
                            self._send_stop()
            except Exception as e:
                self._send_error("unexpected ct2 select error: {0}".format(e))

    @property
    def _device(self):
        return self

    @property
    def card(self):
        return self.__card

    def reset(self):
        self.card.software_reset()
        self.card.reset()
        self.__buffer = []

    def __configure_internal_mode(self):
        card = self.__card

        timer_ct = self.internal_timer_counter
        point_nb_ct = self.internal_point_nb_counter

        timer_inc_stop = getattr(ct2.CtClockSrc, 'INC_CT_{0}_STOP'.format(timer_ct))
        timer_stop_source = getattr(ct2.CtHardStopSrc, 'CT_{0}_EQ_CMP_{0}'.format(timer_ct))
        point_nb_stop_source = getattr(ct2.CtHardStopSrc, 'CT_{0}_EQ_CMP_{0}'.format(point_nb_ct))
        point_nb_gate = getattr(ct2.CtGateSrc, 'CT_{0}_GATE_ENVELOP'.format(point_nb_ct))
        point_nb_start_source = getattr(ct2.CtHardStartSrc, 'CT_{0}_START'.format(point_nb_ct))

        # configure counter 11 as "timer"
        ct_config = ct2.CtConfig(clock_source=ct2.CtClockSrc.CLK_100_MHz,
                                 gate_source=point_nb_gate,
                                 hard_start_source=point_nb_start_source,
                                 hard_stop_source=timer_stop_source,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=False)
        card.set_counter_config(timer_ct, ct_config)
        card.set_counter_comparator_value(timer_ct, int(self.acq_expo_time * 1E8))

        # configure counter 12 as "nb. points"

        ct_config = ct2.CtConfig(clock_source=timer_inc_stop,
                                 gate_source=ct2.CtGateSrc.GATE_CMPT,
                                 hard_start_source=ct2.CtHardStartSrc.SOFTWARE,
                                 hard_stop_source=point_nb_stop_source,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=True)
        card.set_counter_config(point_nb_ct, ct_config)
        card.set_counter_comparator_value(point_nb_ct, self.acq_nb_points)

        # dma transfer and error will trigger DMA; also counter 12 stop
        # should trigger an interrupt (this way we know that the
        # acquisition has finished without having to query the
        # counter 12 status)
        card.set_interrupts(counters=(point_nb_ct,), dma=True, error=True)

        # make master enabled by software
        card.set_counters_software_enable((timer_ct, point_nb_ct))

        # ... and now for the slave channels

        channels = tuple(self.acq_channels)
        all_channels = channels + (timer_ct, point_nb_ct)

        # change the start and stop sources for the active channels
        for ch_nb in channels:
            ct_config = card.get_counter_config(ch_nb)
            ct_config.hard_start_source = point_nb_start_source
            ct_config.hard_stop_source = timer_stop_source
            card.set_counter_config(ch_nb, ct_config)

        # counter 11 will latch all active counters/channels
        latch_sources = dict([(ct, timer_ct) for ct in all_channels])
        card.set_counters_latch_sources(latch_sources)

        # counter 11 counter-to-latch signal will trigger DMA; at each DMA
        # trigger, all active counters (including counters 11 (timer)
        # and 12 (point_nb)) are stored to FIFO
        card.set_DMA_enable_trigger_latch((timer_ct,), all_channels)
        card.set_counters_software_enable(channels)

    def apply_config(self):
        configure_card(self.card, self.card_config)

    def prepare_acq(self):
        if self.acq_mode == AcqMode.Internal:
            self.__configure_internal_mode()
        else:
            raise NotImplementedError

    def start_acq(self):
        if self.acq_mode == AcqMode.Internal:
            counters = self.internal_timer_counter, self.internal_point_nb_counter
            self.card.set_counters_software_start(counters)
        else:
            raise NotImplementedError

    def trigger_latch(self, counters):
        self.card.trigger_counters_software_latch(counters)

    @property
    def acq_mode(self):
        return self.__acq_mode

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self.__acq_mode = AcqMode(acq_mode)

    @property
    def acq_nb_points(self):
        return self.__acq_nb_points

    @acq_nb_points.setter
    def acq_nb_points(self, acq_nb_points):
        self.__acq_nb_points = acq_nb_points

    @property
    def acq_expo_time(self):
        return self.__acq_expo_time

    @acq_expo_time.setter
    def acq_expo_time(self, acq_expo_time):
        self.__acq_expo_time = acq_expo_time

    @property
    def acq_channels(self):
        return self.__acq_channels

    @acq_channels.setter
    def acq_channels(self, acq_channels):
        self.__acq_channels = acq_channels

    @property
    def counters(self):
        return self.card.get_counters_values()

    @property
    def latches(self):
        return self.card.get_latches_values()

    def read_data(self):
        b = self.__buffer
        if b:
            self.__buffer = []
            data = numpy.vstack(b)
        else:
            data = numpy.array([[]], dtype=numpy.uint32)
