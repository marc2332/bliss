# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import numpy
import gevent
from gevent import lock
from gevent import select
from louie import dispatcher

try:
    import enum
except:
    from . import enum34 as enum

from . import ct2


ErrorSignal = "error"
StatusSignal = "status"
PointNbSignal = "point_nb"


class AcqMode(enum.Enum):
    """Acquisition mode enumeration"""

    #: Software start + internal timer trigger readout
    IntTrigReadout = 0

    #: Software start + software trigger readout
    SoftTrigReadout = 1

    #: Software start + internal trigger int exposure
    IntTrigSingle = 2

    #: Software start + software trigger int exposure
    IntTrigMulti = 3


class AcqStatus(enum.Enum):
    """Acquisition status"""

    #: Ready to acquire
    Ready = 0

    #: Acquiring data
    Running = 1


class BaseCT2Device(object):
    """Base abstract class for a CT2Device"""

    internal_timer_counter = 11
    internal_point_nb_counter = 12

    IntClockSrc = {
        1.25E3: ct2.CtClockSrc.CLK_1_25_KHz,
        10E3:   ct2.CtClockSrc.CLK_10_KHz,
        125E3:  ct2.CtClockSrc.CLK_125_KHz,
        1E6:    ct2.CtClockSrc.CLK_1_MHz,
        12.5E6: ct2.CtClockSrc.CLK_12_5_MHz,
        100E6:  ct2.CtClockSrc.CLK_100_MHz,
    }

    def __init__(self, config, name):
        self.__config = config
        self.__name = name

    # helper methods to fire events

    def _send_error(self, error):
        dispatcher.send(ErrorSignal, self, error)

    def _send_point_nb(self, point_nb):
        dispatcher.send(PointNbSignal, self, point_nb)

    def _send_status(self, status):
        dispatcher.send(StatusSignal, self, status)

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
    def acq_status(self):
        return self._device.acq_status

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

    def stop_acq(self):
        self._device.stop_acq()

    def apply_config():
        self._device.apply_config()

    def read_data(self):
        self._device.read_data()

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

    StdModes = [
        AcqMode.IntTrigReadout,
        AcqMode.SoftTrigReadout,
        AcqMode.IntTrigSingle,
        AcqMode.IntTrigMulti,
    ]
    
    DefOutConfig = {'chan': 10, 'level': ct2.Level.TTL}

    def __init__(self, config, name, acq_mode=AcqMode.IntTrigReadout, 
                 out_config=DefOutConfig):
        BaseCT2Device.__init__(self, config, name)
        self.__buffer = []
        self.__buffer_lock = lock.RLock()
        self.__card = self.config.get(self.name)
        self.__acq_mode = acq_mode
        self.__out_config = dict(out_config or {}) 
        self.__acq_status = AcqStatus.Ready
        self.__acq_expo_time = 1.0
        self.__acq_point_period = None
        self.__acq_nb_points = 1
        self.__acq_channels = ()
        self.__timer_freq = 1E8
        self.__event_loop = None
        
        card = self.__card
        if self.out_channel and self.out_channel not in card.OUTPUT_CHANNELS:
            raise ValueError('out_config channels must be in %s', 
                             card.OUTPUT_CHANNELS)


    def __del__(self):
        self.stop_acq()

    def run_acq_loop(self):
        card = self.__card

        int_trig_single = (self.__acq_mode == AcqMode.IntTrigSingle)
        trig_readout = self.__acq_mode in [AcqMode.IntTrigReadout,
                                           AcqMode.SoftTrigReadout]
        timer_ct = self.internal_timer_counter
        out_ct = self.out_counter
        acq_last_point = self.acq_nb_points - 1

        point_nb = -1

        while self.__acq_status == AcqStatus.Running:
            read, write, error = select.select((card,), (), (card,))
            try:
                if error:
                    self._send_error("ct2 select error on {0}".format(error))

                if not read:
                    continue

                ack_irq = card.acknowledge_interrupt()
                (counters, channels, dma, fifo_half_full, err), tstamp = ack_irq

                if err:
                    self._send_error("ct2 error")

                if counters and dma:
                    print "Warning! Overrun: counters=%s, dma=%s" % (counters, \
                                                                     dma)
                if dma:
                    data, fifo_status = card.read_fifo()
                    point_nb = data[-1][-1]
                
                point_end = timer_ct in counters if int_trig_single else dma
                acq_end = point_end and (point_nb == acq_last_point)
                last_restart = point_end and (point_nb == acq_last_point - 1)
                if last_restart and out_ct:
                    ct_config = card.get_counter_config(out_ct)
                    ct_config.hard_start_source = ct2.CtHardStartSrc.SOFTWARE
                    card.set_counter_config(out_ct, ct_config)

                if acq_end:
                    self.__acq_status = AcqStatus.Ready
                    
                if dma:
                    with self.__buffer_lock:
                        self.__buffer.append(data)
                    point_nb = data[-1][-1]
                    self._send_point_nb(point_nb)

                if acq_end:
                    self._send_status(self.__acq_status)
            except Exception as e:
                sys.excepthook(*sys.exc_info())
                self._send_error("unexpected ct2 select error: {0}".format(e))

        card.disable_counters_software(card.COUNTERS)
        card.set_DMA_enable_trigger_latch(reset_fifo_error_flags=True)
        while True:
            read, write, error = select.select((card,), (), (card,), 0)
            if not read:
                break
            ack_irq = card.acknowledge_interrupt()
        card.set_interrupts()
            
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

    def __configure_std_mode(self, mode):
        card = self.__card

        timer_ct = self.internal_timer_counter
        point_nb_ct = self.internal_point_nb_counter
        out_ch = self.out_channel
        out_ct = self.out_counter

        def stop_on_ct_end(ct):
            return getattr(ct2.CtHardStopSrc, 'CT_{0}_EQ_CMP_{0}'.format(ct))

        inc_on_timer_stop = getattr(ct2.CtClockSrc, 
                                    'INC_CT_{0}_STOP'.format(timer_ct))
        start_on_timer_start = getattr(ct2.CtHardStartSrc, 
                                       'CT_{0}_START'.format(timer_ct))
        if self.__has_int_exp():
            timer_stop_source = stop_on_ct_end(timer_ct)
        else:
            timer_stop_source = ct2.CtHardStopSrc.SOFTWARE

        point_nb_stop_source = stop_on_ct_end(point_nb_ct)
        point_nb_gate = getattr(ct2.CtGateSrc, 
                                'CT_{0}_GATE_ENVELOP'.format(point_nb_ct))
        point_nb_start_source = getattr(ct2.CtHardStartSrc, 
                                        'CT_{0}_START'.format(point_nb_ct))

        stop_from_hard_stop = (mode in [AcqMode.IntTrigMulti])

        timer_cmp, out_cmp = self.__get_counter_cmp()
        int_counters = []

        # configure "timer" counter
        timer_clock_source = self.IntClockSrc[self.timer_freq]
        ct_config = ct2.CtConfig(clock_source=timer_clock_source,
                                 gate_source=point_nb_gate,
                                 hard_start_source=point_nb_start_source,
                                 hard_stop_source=timer_stop_source,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=stop_from_hard_stop)
        card.set_counter_config(timer_ct, ct_config)
        if timer_cmp is not None:
            card.set_counter_comparator_value(timer_ct, timer_cmp)

        # timer generates IRQs in IntTrigSingle (point end)
        if mode == AcqMode.IntTrigSingle:
            int_counters.append(timer_ct)

        # configure "nb. points" counter
        ct_config = ct2.CtConfig(clock_source=inc_on_timer_stop,
                                 gate_source=ct2.CtGateSrc.GATE_CMPT,
                                 hard_start_source=ct2.CtHardStartSrc.SOFTWARE,
                                 hard_stop_source=point_nb_stop_source,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=True)
        card.set_counter_config(point_nb_ct, ct_config)
        card.set_counter_comparator_value(point_nb_ct, self.acq_nb_points)

        # make master enabled by software
        card.enable_counters_software((timer_ct, point_nb_ct))

        # ... and now for the slave channels

        channels = tuple(self.acq_channels)
        all_channels = channels + (timer_ct, point_nb_ct)

        # change the start and stop sources for the active channels
        for ch_nb in channels:
            ct_config = card.get_counter_config(ch_nb)
            ct_config.gate_source = point_nb_gate
            ct_config.hard_start_source = start_on_timer_start
            ct_config.hard_stop_source = timer_stop_source
            ct_config.reset_from_hard_soft_stop = True
            ct_config.stop_from_hard_stop = stop_from_hard_stop
            card.set_counter_config(ch_nb, ct_config)

        # if needed, configure the "output" counter
        if out_ct:
            auto_restart = (mode != AcqMode.IntTrigMulti and
                            self.acq_nb_points > 1)
            start_src = 'START_STOP' if auto_restart else 'START'
            out_start_source = getattr(ct2.CtHardStartSrc,
                                       'CT_{0}_%s'.format(timer_ct) % start_src)
            out_stop_source = stop_on_ct_end(out_ct)

            ct_config = ct2.CtConfig(clock_source=timer_clock_source,
                                     gate_source=ct2.CtGateSrc.GATE_CMPT,
                                     hard_start_source=out_start_source,
                                     hard_stop_source=out_stop_source,
                                     reset_from_hard_soft_stop=True,
                                     stop_from_hard_stop=True)
            card.set_counter_config(out_ct, ct_config)
            card.set_counter_comparator_value(out_ct, out_cmp)
            card.enable_counters_software((out_ct,))
            
        # counter that will latch all active counters
        latch_ct = out_ct if out_ct else timer_ct
        latch_sources = dict([(ct, latch_ct) for ct in all_channels])
        card.set_counters_latch_sources(latch_sources)

        # timer counter-to-latch signal will trigger DMA; at each DMA
        # trigger, all active counters (including timer and point_nb counters)
        # are stored to FIFO
        card.set_DMA_enable_trigger_latch((timer_ct,), all_channels)

        # dma transfer and error will also trigger DMA
        card.set_interrupts(counters=int_counters, dma=True, error=True)

        # enable the active counters
        card.enable_counters_software(channels)

        # and finally the output channel
        if out_ch:
            ch_source = card.get_output_channels_source()
            ch_source[out_ch] = getattr(ct2.OutputSrc, 
                                        'CT_{0}_GATE'.format(out_ch))
            card.set_output_channels_source(ch_source)
            filter_pol = card.get_output_channels_filter()
            filter_pol[out_ch]["polarity_inverted"] = False
            card.set_output_channels_filter(filter_pol)
            def_out_level = self.DefOutConfig['level']
            ch_level = card.get_output_channels_level()
            ch_level[out_ch] = self.__out_config.get('level', def_out_level)
            card.set_output_channels_level(ch_level)
            
    def __get_counter_cmp(self):
        expo_time = (self.acq_expo_time or 0) * self.timer_freq
        point_period = (self.acq_point_period or 0) * self.timer_freq

        if not point_period:
            point_period = expo_time
            int_trig_multi = self.acq_mode == AcqMode.IntTrigMulti
            expo_time = point_period - (0 if int_trig_multi else 1)

        timer_cmp, out_cmp = None, None
        if self.__has_int_exp():
            timer_cmp = int(point_period)
        if self.out_counter:
            out_cmp = int(expo_time)

        return timer_cmp, out_cmp

    def __has_int_exp(self):
        return self.acq_mode in [AcqMode.IntTrigReadout, AcqMode.IntTrigSingle, 
                                 AcqMode.IntTrigMulti]
        
    def apply_config(self):
        ct2.configure_card(self.card, self.card_config)

    def prepare_acq(self):
        has_period = (self.acq_point_period > 0)
        if self.acq_mode == AcqMode.IntTrigSingle:
            if not self.out_channel:
                raise ValueError('IntTrigSingle requires out_config')
            if not has_period:
                raise ValueError('IntTrigSingle must define acq. point period')
            elif self.acq_point_period <= self.acq_expo_time:
                raise ValueError('Acq. point period must be greater than expo.')
        elif has_period:
            raise ValueError('Acq. point period only allowed in IntTrigSingle')

        self.stop_acq()
        if self.acq_mode in self.StdModes:
            self.__configure_std_mode(self.acq_mode)
        else:
            raise NotImplementedError

    def start_acq(self):
        self.__acq_status = AcqStatus.Running
        try:
            self.__event_loop = gevent.spawn(self.run_acq_loop)

            if self.acq_mode in self.StdModes:
                counters = (self.internal_point_nb_counter,)
                self.card.start_counters_software(counters)
            else:
                raise NotImplementedError
        except:
            self.__acq_status = AcqStatus.Ready
            raise
        self._send_status(self.__acq_status)

    def stop_acq(self):
        if self.__acq_status != AcqStatus.Running:
            if self.__event_loop is not None:
                gevent.wait([self.__event_loop])
            self.__event_loop = None
            return

        self.__acq_status = AcqStatus.Ready
        if self.acq_mode in self.StdModes:
            if self.out_counter:
                self.card.disable_counters_software((self.out_counter,))
            self.card.stop_counters_software(self.card.COUNTERS)
        else:
            raise NotImplementedError
        gevent.wait([self.__event_loop])
        self.__event_loop = None
        self._send_status(self.__acq_status)

    def trigger_latch(self, counters):
        self.card.trigger_counters_software_latch(counters)

    def trigger_point(self):
        if self.acq_mode == AcqMode.SoftTrigReadout:
            self.card.stop_counters_software((self.internal_timer_counter,))
        elif self.acq_mode == AcqMode.IntTrigMulti:
            counters_status = self.card.get_counters_status()
            if counters_status[self.internal_timer_counter]['run']:
                raise RuntimeError('Counter still running')
            self.card.start_counters_software((self.internal_timer_counter,))
        else:
            raise NotImplementedError

    @property
    def acq_mode(self):
        return self.__acq_mode

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self.__acq_mode = AcqMode(acq_mode)

    @property
    def acq_status(self):
        return self.__acq_status

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
    def acq_point_period(self):
        return self.__acq_point_period

    @acq_point_period.setter
    def acq_point_period(self, acq_point_period):
        self.__acq_point_period = acq_point_period

    @property
    def acq_channels(self):
        return self.__acq_channels

    @acq_channels.setter
    def acq_channels(self, acq_channels):
        self.__acq_channels = acq_channels

    @property
    def timer_freq(self):
        return self.__timer_freq

    @timer_freq.setter
    def timer_freq(self, timer_freq):
        if timer_freq not in self.IntClockSrc:
            raise ValueError('Invalid timer clock: %s' % timer_freq)
        self.__timer_freq = timer_freq

    @property
    def out_channel(self):
        return self.__out_config["chan"] if self.__out_config else None

    @property
    def out_counter(self):
        return self.out_channel
                                 
    @property
    def counters(self):
        return self.card.get_counters_values()

    @property
    def latches(self):
        return self.card.get_latches_values()

    def read_data(self):
        with self.__buffer_lock:
            return self.__read_data()

    def __read_data(self):
        b = self.__buffer
        if b:
            self.__buffer = []
            data = numpy.vstack(b)
        else:
            data = numpy.array([[]], dtype=numpy.uint32)
        return data
