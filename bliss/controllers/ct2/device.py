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

    #: External start + internal trigger int exposure
    ExtTrigSingle = 4

    #: External start + external trigger int exposure
    ExtTrigMulti = 5

    #: External start + external trigger ext exposure
    ExtGate = 6

    #: External start + external trigger readout
    ExtTrigReadout = 7


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

    # helper methods to fire events

    def _send_error(self, error):
        dispatcher.send(ErrorSignal, self, error)

    def _send_point_nb(self, point_nb):
        dispatcher.send(PointNbSignal, self, point_nb)

    def _send_status(self, status):
        dispatcher.send(StatusSignal, self, status)

    @property
    def config(self):
        return self._device.config

    @property
    def card_config(self):
        return self._device.card_config

    @property
    def name(self):
        return self._device.name

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
        return AcqMode[self._device.acq_mode]

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self._device.acq_mode = acq_mode

    @property
    def acq_status(self):
        return AcqStatus[self._device.acq_status]

    @property
    def acq_nb_points(self):
        return self._device.acq_nb_points

    @acq_nb_points.setter
    def acq_nb_points(self, acq_nb_points):
        self._device.acq_nb_points = acq_nb_points

    @property
    def timer_freq(self):
        return self._device.timer_freq

    @timer_freq.setter
    def timer_freq(self, timer_freq):
        self._device.timer_freq = timer_freq

    @property
    def acq_expo_time(self):
        return self._device.acq_expo_time

    @acq_expo_time.setter
    def acq_expo_time(self, acq_expo_time):
        self._device.acq_expo_time = acq_expo_time

    @property
    def acq_channels(self):
        return tuple(self._device.acq_channels)

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

    def trigger_latch(self, counters):
        self._device.trigger_latch(counters)

    def trigger_point(self):
        self._device.trigger_point()

    def dump_memory(self):
        return self._device.dump_memory()

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
        AcqMode.ExtTrigSingle,
        AcqMode.ExtTrigMulti,
        AcqMode.ExtGate,
        AcqMode.ExtTrigReadout,
    ]

    SoftStartModes = [
        AcqMode.IntTrigReadout,
        AcqMode.SoftTrigReadout,
        AcqMode.IntTrigSingle,
        AcqMode.IntTrigMulti,
    ]

    IntTrigModes = [
        AcqMode.IntTrigReadout, 
        AcqMode.IntTrigSingle,
        AcqMode.ExtTrigSingle,
    ]

    IntTrigDeadTimeModes = [
        AcqMode.IntTrigSingle,
        AcqMode.ExtTrigSingle,
    ]

    IntExpModes = [
        AcqMode.IntTrigReadout, 
        AcqMode.IntTrigSingle, 
        AcqMode.IntTrigMulti, 
        AcqMode.ExtTrigSingle, 
        AcqMode.ExtTrigMulti,
    ]

    ExtStartModes = [
        AcqMode.ExtTrigSingle, 
        AcqMode.ExtTrigMulti, 
        AcqMode.ExtGate,
        AcqMode.ExtTrigReadout,
    ]

    ExtTrigModes = [
        AcqMode.ExtTrigMulti, 
        AcqMode.ExtGate,
    ]

    ExtExpModes = [
        AcqMode.ExtGate,
        AcqMode.ExtTrigReadout,
    ]

    OutGateModes = [
        AcqMode.IntTrigSingle,
        AcqMode.IntTrigMulti,
        AcqMode.ExtTrigSingle,
    ]

    ZeroDeadTimeModes = [
        AcqMode.IntTrigReadout, 
        AcqMode.IntTrigMulti,
    ]

    DefChanLevel = ct2.Level.TTL
    DefInConfig = {'level': DefChanLevel, '50ohm': False,
                   'polarity_invert': False}
    DefOutConfig = {'chan': 10, 'level': DefChanLevel}

    def __init__(self, card=None, card_config=None, config=None, name=None,
                 acq_mode=AcqMode.IntTrigReadout, in_config=None,
                 out_config=DefOutConfig):
        BaseCT2Device.__init__(self)

        if card_config is None:
            if name is None:
                raise ValueError('Must provide name to create card')
            if config is None:
                import bliss.config.static
                config = bliss.config.static.get_config()
            card_config = config.get_config(name)
        if card is None:
            if config is None or name is None:
                card = ct2.P201Card()
                ct2.configure_card(card, card_config)
            else:                    
                card = config.get(name)
            
        self.__buffer = []
        self.__buffer_lock = lock.RLock()
        self.__name = name
        self.__card = card
        self.__card_config = card_config
        self.__acq_mode = acq_mode
        self.__in_config = dict(in_config or {})
        self.__out_config = dict(out_config or {})
        self.__acq_status = AcqStatus.Ready
        self.__acq_expo_time = 1.0
        self.__acq_point_period = None
        self.__acq_nb_points = 1
        self.__acq_channels = ()
        self.__timer_freq = 1E8
        self.__event_loop = None
        self.__trigger_on_start = True
        self.__soft_started = False

        card = self.card
        if self.out_channel and self.out_channel not in card.OUTPUT_CHANNELS:
            raise ValueError('out_config channels must be in %s', 
                             card.OUTPUT_CHANNELS)

    def __del__(self):
        self.stop_acq()

    def run_acq_loop(self):
        card = self.card

        int_trig_dead_time = self.__acq_mode in self.IntTrigDeadTimeModes
        timer_ct = self.internal_timer_counter
        out_ct = self.out_counter
        acq_last_point = self.acq_nb_points - 1

        point_nb = -1
        first_discarded = False
        async_latch_comp = 0
        
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

                timer_end = (timer_ct in counters)
                acq_running = (self.__acq_status == AcqStatus.Running)
                if int_trig_dead_time and timer_end and dma and acq_running:
                    print "Warning! Overrun: counters=%s, dma=%s" % (counters, \
                                                                     dma)
                if dma:
                    data, fifo_status = card.read_fifo()
                    # software trigger readout is asynchronous with the int.
                    # clocks, so counter point_nb & latch are not properly
                    # synchronised, correct the this effect
                    if self.__acq_mode == AcqMode.SoftTrigReadout:
                        data = numpy.array(data)
                        for i, point_data in enumerate(data, point_nb + 1):
                            async_latch_comp = point_data[-1] - i
                            if async_latch_comp not in [0, 1]:
                                print ("Warning! Async latch jump: %s" %
                                       async_latch_comp)
                            point_data[-1] -= async_latch_comp
                    elif self.__in_ext_trig_readout():
                        if not first_discarded:
                            data = numpy.array(data[1:])
                            first_discarded = True
                            dma = len(data) > 0
                        if dma and first_discarded:
                            data = numpy.array(data)
                            for point_data in data:
                                point_data[-1] -= 1
                if dma:
                    point_nb = data[-1][-1]
                point_end = timer_end if int_trig_dead_time else dma
                acq_end = point_end and (point_nb == acq_last_point)
                last_restart = point_end and (point_nb == acq_last_point - 1)
                if out_ct and last_restart and self.__has_int_trig():
                    ct_config = card.get_counter_config(out_ct)
                    ct_config.hard_start_source = ct2.CtHardStartSrc.SOFTWARE
                    card.set_counter_config(out_ct, ct_config)

                if acq_end:
                    self.__acq_status = AcqStatus.Ready
                    
                if dma:
                    with self.__buffer_lock:
                        self.__buffer.append(data)
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

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.card_config and self.card_config._config

    @property
    def card_config(self):
        return self.__card_config

    def reset(self):
        self.card.software_reset()
        self.card.reset()
        self.__buffer = []

    def __configure_std_mode(self, mode):
        card = self.card

        timer_ct = self.internal_timer_counter
        point_nb_ct = self.internal_point_nb_counter
        in_ch = self.in_channel
        in_ct = self.in_counter
        out_ch = self.out_channel
        out_ct = self.out_counter

        timer_clock_source = self.IntClockSrc[self.timer_freq]

        out_gate = (mode in self.OutGateModes)
        gate_ct = out_ct if (out_ct and out_gate) else timer_ct

        ext_trig_readout = self.__in_ext_trig_readout()

        def ch_signal(ch, rise, pol_invert=False):
            edge = 'RISING' if bool(rise) != bool(pol_invert) else 'FALLING'
            return 'CH_{0}_{1}_EDGE'.format(ch, edge)

        def ct_gate(ct):
            return getattr(ct2.CtGateSrc, 'CT_{0}_GATE_ENVELOP'.format(ct))
        def start_source(signal):
            return getattr(ct2.CtHardStartSrc, signal)
        def stop_source(signal):
            return getattr(ct2.CtHardStopSrc, signal)
        def start_on_ct_signal(ct, signal):
            return start_source('CT_{0}_{1}'.format(ct, signal))
        def stop_on_ct_end(ct):
            return stop_source('CT_{0}_EQ_CMP_{0}'.format(ct))
        def stop_on_ct_stop(ct):
            return stop_source('CT_{0}_STOP'.format(ct))
        
        if in_ch:
            def_chan_level = self.DefInConfig['level']
            ch_level = card.get_input_channels_level()
            ch_level[in_ch] = self.__in_config.get('level', def_chan_level)
            card.set_input_channels_level(ch_level)
            def_chan_50ohm = self.DefInConfig['50ohm']
            ch_50ohm = card.get_input_channels_50ohm_adapter()
            ch_50ohm[in_ch] = self.__in_config.get('50ohm', def_chan_50ohm)
            card.set_input_channels_50ohm_adapter(ch_50ohm)
            def_chan_pol_inv = self.DefInConfig['polarity_invert']
            ch_pol_invert = self.__in_config.get('polarity_invert',
                                                 def_chan_pol_inv)

            ext_rise_signal = ch_signal(in_ch, True, ch_pol_invert)
            ext_fall_signal = ch_signal(in_ch, False, ch_pol_invert)

        # in_counter is used to generate, on the ext. event, an internal pulse
        # that triggers the timer stop synchronously with the internal clocks
        if in_ct:
            # the ext. event: ext_trig=rising-edge, ext_gate=falling-edge
            ext_gate = (mode == AcqMode.ExtGate)
            in_start_signal = ext_fall_signal if ext_gate else ext_rise_signal
            in_start_source = start_source(in_start_signal)

            ct_config = ct2.CtConfig(clock_source=timer_clock_source,
                                     gate_source=ct_gate(point_nb_ct),
                                     hard_start_source=in_start_source,
                                     hard_stop_source=stop_on_ct_end(in_ct),
                                     reset_from_hard_soft_stop=True,
                                     stop_from_hard_stop=True)
            card.set_counter_config(in_ct, ct_config)
            card.set_counter_comparator_value(in_ct, 1)
            card.enable_counters_software((in_ct,))
            
        auto_restart = ((self.__has_int_trig() or ext_trig_readout) and
                        (self.acq_nb_points > 1))
        stop_from_hard_stop = not auto_restart

        if self.__has_ext_start():
            timer_start_source = start_source(ext_rise_signal)
        else:
            timer_start_source = start_source('SOFTWARE')
            
        if self.__has_int_exp():
            timer_stop_source = stop_on_ct_end(timer_ct)
        elif self.__has_ext_exp():
            timer_stop_source = stop_on_ct_end(in_ct)
        else:
            timer_stop_source = stop_source('SOFTWARE')

        timer_cmp, out_cmp = self.__get_counter_cmp()
        irq_counters = []

        # configure "timer" counter
        ct_config = ct2.CtConfig(clock_source=timer_clock_source,
                                 gate_source=ct_gate(point_nb_ct),
                                 hard_start_source=timer_start_source,
                                 hard_stop_source=timer_stop_source,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=stop_from_hard_stop)
        card.set_counter_config(timer_ct, ct_config)
        if timer_cmp is not None:
            card.set_counter_comparator_value(timer_ct, timer_cmp)

        # timer generates IRQs in int-trig-with-dead-time modes (point end)
        if mode in self.IntTrigDeadTimeModes:
            irq_counters.append(timer_ct)

        # configure "nb. points" counter
        inc_on_timer_stop = getattr(ct2.CtClockSrc, 
                                    'INC_CT_{0}_STOP'.format(timer_ct))
        ct_config = ct2.CtConfig(clock_source=inc_on_timer_stop,
                                 gate_source=ct2.CtGateSrc.GATE_CMPT,
                                 hard_start_source=start_source('SOFTWARE'),
                                 hard_stop_source=stop_on_ct_end(point_nb_ct),
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=True)
        card.set_counter_config(point_nb_ct, ct_config)
        acq_nb_points = self.acq_nb_points + (1 if ext_trig_readout else 0)
        card.set_counter_comparator_value(point_nb_ct, acq_nb_points)
        # gen. IRQ on point_nb (soft) stop, so acq_loop ends during stop_acq
        irq_counters.append(point_nb_ct)

        # make master enabled by software
        card.enable_counters_software((timer_ct, point_nb_ct))

        # ... and now for the slave channels

        channels = tuple(self.acq_channels)
        all_channels = channels + (timer_ct, point_nb_ct)

        integrator = dict([(ct, False) for ct in channels])
        # change the start and stop sources for the active channels
        for ch_nb in channels:
            ct_config = card.get_counter_config(ch_nb)
            ct_config.gate_source = ct_gate(gate_ct)
            ct_config.hard_start_source = start_on_ct_signal(timer_ct, 'START')
            ct_config.hard_stop_source = stop_on_ct_stop(timer_ct)
            ct_config.reset_from_hard_soft_stop = not integrator[ch_nb]
            ct_config.stop_from_hard_stop = stop_from_hard_stop
            card.set_counter_config(ch_nb, ct_config)

        # if needed, configure the "output" counter
        if out_ct:
            start_signal = 'START_STOP' if auto_restart else 'START'
            out_start_source = start_on_ct_signal(timer_ct, start_signal)

            if ext_trig_readout:
                out_stop_source = stop_source(ext_rise_signal)
            elif out_cmp:
                out_stop_source = stop_on_ct_end(out_ct)
            elif self.__has_ext_exp():
                out_stop_source = stop_on_ct_end(in_ct)
            else:
                out_stop_source = stop_on_ct_stop(timer_ct)
            ct_config = ct2.CtConfig(clock_source=timer_clock_source,
                                     gate_source=ct_gate(timer_ct),
                                     hard_start_source=out_start_source,
                                     hard_stop_source=out_stop_source,
                                     reset_from_hard_soft_stop=True,
                                     stop_from_hard_stop=True)
            card.set_counter_config(out_ct, ct_config)
            if out_cmp:
                card.set_counter_comparator_value(out_ct, out_cmp)
            card.enable_counters_software((out_ct,))
            
        # gate counter will latch all active counters at stop
        latch_sources = dict([(ct, gate_ct) for ct in all_channels])
        card.set_counters_latch_sources(latch_sources)

        # timer counter-to-latch signal will trigger DMA; at each DMA
        # trigger, all active counters (including timer and point_nb counters)
        # are stored to FIFO
        card.set_DMA_enable_trigger_latch((timer_ct,), all_channels)

        # dma transfer and error will also trigger DMA
        card.set_interrupts(counters=irq_counters, dma=True, error=True)

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

        if not point_period and expo_time:
            # in zero-dead-time modes the out_counter counts one pulse less
            # so it can be restarted on timer end
            longer_timer = self.acq_mode in self.ZeroDeadTimeModes
            extra_gap = longer_timer and self.out_counter
            point_period = expo_time + (1 if extra_gap else 0)

        timer_cmp, out_cmp = None, None
        if self.__has_int_exp():
            timer_cmp = int(point_period)
            if self.out_counter:
                out_cmp = int(expo_time)

        return timer_cmp, out_cmp

    def __has_soft_start(self):
        return self.acq_mode in self.SoftStartModes

    def __has_int_trig(self):
        return self.acq_mode in self.IntTrigModes

    def __has_int_exp(self):
        return self.acq_mode in self.IntExpModes
        
    def __has_ext_start(self):
        return self.acq_mode in self.ExtStartModes

    def __has_ext_trig(self):
        return self.acq_mode in self.ExtTrigModes

    def __has_ext_exp(self):
        return self.acq_mode in self.ExtExpModes

    def __in_ext_trig_readout(self):
        return self.acq_mode == AcqMode.ExtTrigReadout

    def apply_config(self):
        ct2.configure_card(self.card, self.card_config)

    def prepare_acq(self):
        has_period = (self.acq_point_period > 0)
        mode_str = 'int-trig-with-dead-time'
        if self.acq_mode in self.IntTrigDeadTimeModes:
            if not self.out_channel:
                raise ValueError('%s requires out_config' % mode_str)
            if not has_period:
                raise ValueError('%s must define acq. point period' % mode_str)
            elif self.acq_point_period <= self.acq_expo_time:
                raise ValueError('Acq. point period must be greater than expo.')
        elif has_period:
            raise ValueError('Acq. point period only allowed in %s' % mode_str)
        if self.__has_ext_trig() and not self.in_channel:
            raise ValueError('Must provide in_config in ext-trig modes')

        self.stop_acq()
        if self.acq_mode not in self.StdModes:
            raise NotImplementedError

        self.__configure_std_mode(self.acq_mode)
        self.__soft_started = False

        self._send_point_nb(-1)

    def __on_acq_loop_finished(self, event_loop):
        self.__event_loop = None

    def start_acq(self):
        if self.acq_mode not in self.StdModes:
            raise NotImplementedError

        self.__acq_status = AcqStatus.Running
        try:
            self.__event_loop = gevent.spawn(self.run_acq_loop)
            self.__event_loop.link(self.__on_acq_loop_finished)

            counters = (self.internal_point_nb_counter,)
            self.card.start_counters_software(counters)

            if self.__has_soft_start() and self.__trigger_on_start:
                self.trigger_point()
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

        # signal acq_loop that we are stopping
        self.__acq_status = AcqStatus.Ready
        if self.out_counter:
            self.card.disable_counters_software((self.out_counter,))
        # this will generate point_nb_cnt STOP -> IRQ -> unblock acq_loop
        self.card.stop_counters_software(self.card.COUNTERS)

        gevent.wait([self.__event_loop])
        self.__event_loop = None
        self._send_status(self.__acq_status)

    def wait_acq(self):
        if self.__event_loop:
            gevent.wait([self.__event_loop])

    def trigger_latch(self, counters):
        self.card.trigger_counters_software_latch(counters)

    def trigger_point(self):
        if self.acq_status != AcqStatus.Running:
            raise ValueError('No acquisition is running')
        elif self.__has_soft_start() and not self.__soft_started:
            pass
        elif self.__has_int_trig():
            raise ValueError('Cannot trigger point in int-trig modes')

        counters = (self.internal_timer_counter,)
        restart = True
        if self.acq_mode == AcqMode.SoftTrigReadout:
            point_nb_ct = self.internal_point_nb_counter
            point_nb = self.card.get_counter_value(point_nb_ct)
            self.card.stop_counters_software(counters)
            start = not self.__soft_started
            restart = start or (point_nb < self.acq_nb_points - 1)
        elif self.acq_mode == AcqMode.IntTrigMulti:
            counters_status = self.card.get_counters_status()
            if counters_status[counters[0]]['run']:
                raise RuntimeError('Counter still running')

        if self.__has_soft_start():
            self.__soft_started = True

        if restart:
            self.card.start_counters_software(counters)

    def dump_memory(self):
        return self.card.dump_memory()

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
    def in_channel(self):
        return self.__in_config["chan"] if self.__in_config else None

    @property
    def in_counter(self):
        return self.in_channel

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
