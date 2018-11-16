# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
CT2 (P201/C208) ESRF PCI counter card device

Minimalistic configuration example:

.. code-block:: yaml

   plugin: ct2
   name: p201
   class: CT2
   type: P201
   address: /dev/ct2_0


(for the complete CT2 YAML_ specification see :ref:`bliss-ct2-yaml`)
"""


import sys
import enum
import logging
import functools

import numpy
import gevent
from gevent import lock
from gevent import select
from louie import dispatcher


from . import card


ErrorSignal = "error"
StatusSignal = "status"
PointNbSignal = "point_nb"


class AcqMode(enum.IntEnum):
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


class AcqStatus(enum.IntEnum):
    """Acquisition status"""

    #: Ready to acquire
    Ready = 0

    #: Acquiring data
    Running = 1


class CT2(object):
    """
    Helper for a locally installed CT2 card (P201/C208).
    """

    # Class attributes

    internal_timer_counter = 11
    internal_point_nb_counter = 12

    IntClockSrc = {
        1.25E3: card.CtClockSrc.CLK_1_25_KHz,
        10E3: card.CtClockSrc.CLK_10_KHz,
        125E3: card.CtClockSrc.CLK_125_KHz,
        1E6: card.CtClockSrc.CLK_1_MHz,
        12.5E6: card.CtClockSrc.CLK_12_5_MHz,
        100E6: card.CtClockSrc.CLK_100_MHz,
    }

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

    IntTrigDeadTimeModes = [AcqMode.IntTrigSingle, AcqMode.ExtTrigSingle]

    IntExpModes = [
        AcqMode.IntTrigReadout,
        AcqMode.IntTrigSingle,
        AcqMode.IntTrigMulti,
        AcqMode.ExtTrigSingle,
        AcqMode.ExtTrigMulti,
    ]

    ExtTrigModes = [AcqMode.ExtTrigMulti, AcqMode.ExtGate, AcqMode.ExtTrigReadout]

    ExtExpModes = [AcqMode.ExtGate, AcqMode.ExtTrigReadout]

    OutGateModes = [AcqMode.IntTrigSingle, AcqMode.IntTrigMulti, AcqMode.ExtTrigSingle]

    ZeroDeadTimeModes = [AcqMode.IntTrigReadout, AcqMode.IntTrigMulti]

    DefaultAcqMode = AcqMode.IntTrigReadout
    DefaultInputConfig = {"channel": None, "polarity inverted": False, "counter": None}
    DefaultOutputConfig = {"channel": 10, "counter": 10}

    def __init__(self, card):
        self._log = logging.getLogger(type(self).__name__)
        self._card = card
        self.__buffer = []
        self.__buffer_lock = lock.RLock()
        self.__acq_mode = self.DefaultAcqMode
        self.__acq_status = AcqStatus.Ready
        self.__acq_expo_time = 1.0
        self.__acq_point_period = None
        self.__acq_nb_points = 1
        self.__acq_channels = ()
        self.__timer_freq = 12.5E6
        self.__event_loop = None
        self.__trigger_on_start = True
        self.__soft_started = False
        self.__last_point_nb = -1
        self.__last_error = None
        self.input_config = dict(self.DefaultInputConfig)
        self.output_config = dict(self.DefaultOutputConfig)

    def close(self):
        self.stop_acq()

    def __getattr__(self, key):
        return getattr(self._card, key)

    def __dir__(self):
        return dir(type(self)) + dir(self._card)

    # helper methods to fire events

    def _send_error(self, error):
        dispatcher.send(ErrorSignal, self, error)

    def _send_point_nb(self, point_nb):
        dispatcher.send(PointNbSignal, self, point_nb)

    def _send_status(self, status):
        dispatcher.send(StatusSignal, self, status)

    def run_acq_loop(self):
        card_o = self._card
        int_trig_dead_time = self.__acq_mode in self.IntTrigDeadTimeModes
        timer_ct = self.internal_timer_counter
        point_nb_ct = self.internal_point_nb_counter
        out_ct = self.output_counter
        not_endless = not self.is_endless_acq
        acq_last_point = self.acq_nb_points - 1

        point_nb = -1
        first_discarded = False
        async_latch_comp = 0

        fifo_persistent_status = {}

        def get_fifo_status():
            fifo_status = self.get_FIFO_status()
            for k in "overrun_error", "write_error", "read_error", "full":
                if fifo_status[k]:
                    fifo_persistent_status[k] = True
            return fifo_status

        while self.__acq_status == AcqStatus.Running:
            # if counters stopped and FIFO is empty select will block forever
            counters_status = card_o.get_counters_status()
            if not counters_status[point_nb_ct]["run"]:
                max_events, nb_counters = card_o.calc_fifo_events(get_fifo_status())
                if not max_events:
                    self._send_error("data overrun")
                    self.__acq_status = AcqStatus.Ready
                    self._send_status(self.__acq_status)
                    break
            read, write, error = select.select((card_o,), (), (card_o,))
            try:
                if error:
                    self.__last_error = "ct2 select error on {0}".format(error)
                    self._send_error(self.__last_error)

                if not read:
                    continue

                ack_irq = card_o.acknowledge_interrupt()
                (counters, channels, dma, fifo_half_full, err), tstamp = ack_irq

                if err:
                    self.__last_error = "ct2 error"
                    self._send_error(self.__last_error)
                if fifo_half_full:
                    self._log.warning("Fifo half full!")

                timer_end = timer_ct in counters
                acq_running = self.__acq_status == AcqStatus.Running
                it_dt_overrun = int_trig_dead_time and timer_end and dma and acq_running
                if it_dt_overrun:
                    self._log.debug("overrun: counters=%s, dma=%s", counters, dma)
                got_data = False

                max_events, nb_counters = card_o.calc_fifo_events(get_fifo_status())
                if max_events > 0:
                    got_data = True
                    data = []
                    while True:
                        single_data, fifo_status = card_o.read_fifo(get_fifo_status())
                        if single_data is None:
                            break
                        data.append(single_data)
                    if len(data) > 1:
                        data = numpy.vstack(data)
                    elif data:
                        data = data[0]
                    else:
                        got_data = False

                if got_data:
                    # software trigger readout is asynchronous with the int.
                    # clocks, so counter point_nb & latch are not properly
                    # synchronised, correct this effect

                    if not_endless and (len(data) + point_nb > acq_last_point):
                        data = data[: acq_last_point - point_nb]
                    sys.stdout.flush()
                    if self.__acq_mode == AcqMode.SoftTrigReadout:
                        data = numpy.array(data)
                        for i, point_data in enumerate(data, point_nb + 1):
                            async_latch_comp = point_data[-1] - i
                            if async_latch_comp not in [0, 1]:
                                self._log.warning(
                                    "warning! Async latch jump: %s", async_latch_comp
                                )
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
                if got_data:
                    point_nb = data[-1][-1]
                point_end = timer_end if int_trig_dead_time else (dma or got_data)
                acq_end = not_endless and point_end and (point_nb == acq_last_point)
                # avoid extra pulse due to re-start of output counter at last point end
                if out_ct and self.__has_int_trig() and point_end:
                    # int_trig_dead_time overrun -> point_nb already incremented
                    curr_point_nb = point_nb + (1 if not it_dt_overrun else 0)
                    if not_endless and (curr_point_nb == acq_last_point):
                        ct_config = card_o.get_counter_config(out_ct)
                        ct_config["hard_start_source"] = card.CtHardStartSrc.SOFTWARE
                        card_o.set_counter_config(out_ct, ct_config)

                if acq_end:
                    self.__acq_status = AcqStatus.Ready

                if got_data:
                    with self.__buffer_lock:
                        self.__buffer.extend(data)
                    self.__last_point_nb = point_nb
                    self._send_point_nb(point_nb)

                if acq_end:
                    self._send_status(self.__acq_status)
            except Exception as e:
                sys.excepthook(*sys.exc_info())
                self.__last_error = "unexpected ct2 select error: {0}".format(e)
                self._send_error(self.__last_error)

        if fifo_persistent_status:
            self._log.error("fifo_persistent_status=%s", fifo_persistent_status)

        card_o.disable_counters_software(card_o.COUNTERS)
        card_o.set_DMA_enable_trigger_latch(reset_fifo_error_flags=True)
        while True:
            read, write, error = select.select((card_o,), (), (card_o,), 0)
            if not read:
                break
            ack_irq = card_o.acknowledge_interrupt()
        card_o.set_interrupts()

    @property
    def event_loop(self):
        return self.__event_loop

    def reset(self):
        self._card.software_reset()
        self._card.reset()
        self.__buffer = []

    def __configure_std_mode(self, mode):
        card_o = self._card
        timer_ct = self.internal_timer_counter
        point_nb_ct = self.internal_point_nb_counter
        in_trig_ch = self.input_channel
        in_ct = self.input_counter
        out_gate_ch = self.output_channel
        out_ct = self.output_counter
        not_endless = not self.is_endless_acq

        timer_clock_source = self.IntClockSrc[self.timer_freq]

        out_gate = mode in self.OutGateModes
        gate_ct = out_ct if (out_ct and out_gate) else timer_ct

        ext_trig_readout = self.__in_ext_trig_readout()

        def ch_signal(ch, rise, pol_invert=False):
            edge = "RISING" if bool(rise) != bool(pol_invert) else "FALLING"
            return "CH_{0}_{1}_EDGE".format(ch, edge)

        def ct_gate(ct):
            return getattr(card.CtGateSrc, "CT_{0}_GATE_ENVELOP".format(ct))

        def start_source(signal):
            return getattr(card.CtHardStartSrc, signal)

        def stop_source(signal):
            return getattr(card.CtHardStopSrc, signal)

        def start_on_ct_signal(ct, signal):
            return start_source("CT_{0}_{1}".format(ct, signal))

        def stop_on_ct_end(ct):
            return stop_source("CT_{0}_EQ_CMP_{0}".format(ct))

        def stop_on_ct_stop(ct):
            return stop_source("CT_{0}_STOP".format(ct))

        if in_trig_ch:
            polarity_inverted = self.input_config["polarity inverted"]
            ext_rise_signal = ch_signal(in_trig_ch, True, polarity_inverted)
            ext_fall_signal = ch_signal(in_trig_ch, False, polarity_inverted)

        # input_counter is used to generate, on the ext. event, an internal pulse
        # that triggers the timer stop synchronously with the internal clocks
        if in_ct:
            # the ext. event: ext_trig=rising-edge, ext_gate=falling-edge
            ext_gate = mode == AcqMode.ExtGate
            in_start_signal = ext_fall_signal if ext_gate else ext_rise_signal
            in_start_source = start_source(in_start_signal)

            ct_config = card.CtConfig(
                clock_source=timer_clock_source,
                gate_source=ct_gate(point_nb_ct),
                hard_start_source=in_start_source,
                hard_stop_source=stop_on_ct_end(in_ct),
                reset_from_hard_soft_stop=True,
                stop_from_hard_stop=True,
            )
            card_o.set_counter_config(in_ct, ct_config)
            card_o.set_counter_comparator_value(in_ct, 1)
            card_o.enable_counters_software((in_ct,))

        multi_points = self.acq_nb_points != 1
        auto_restart = (self.__has_int_trig() or ext_trig_readout) and multi_points
        stop_from_hard_stop = not auto_restart

        if self.__has_ext_start():
            timer_start_source = start_source(ext_rise_signal)
        else:
            timer_start_source = start_source("SOFTWARE")

        if self.__has_int_exp():
            timer_stop_source = stop_on_ct_end(timer_ct)
        elif self.__has_ext_exp():
            timer_stop_source = stop_on_ct_end(in_ct)
        else:
            timer_stop_source = stop_source("SOFTWARE")

        timer_cmp, out_cmp = self.__get_counter_cmp()
        irq_counters = []

        # configure "timer" counter
        ct_config = card.CtConfig(
            clock_source=timer_clock_source,
            gate_source=ct_gate(point_nb_ct),
            hard_start_source=timer_start_source,
            hard_stop_source=timer_stop_source,
            reset_from_hard_soft_stop=True,
            stop_from_hard_stop=stop_from_hard_stop,
        )
        card_o.set_counter_config(timer_ct, ct_config)
        if timer_cmp is not None:
            card_o.set_counter_comparator_value(timer_ct, timer_cmp)

        # timer generates IRQs in int-trig-with-dead-time modes (point end)
        if mode in self.IntTrigDeadTimeModes:
            irq_counters.append(timer_ct)

        # configure "nb. points" counter
        inc_on_timer_stop = getattr(card.CtClockSrc, "INC_CT_{0}_STOP".format(timer_ct))
        ct_config = card.CtConfig(
            clock_source=inc_on_timer_stop,
            gate_source=card.CtGateSrc.GATE_CMPT,
            hard_start_source=start_source("SOFTWARE"),
            hard_stop_source=stop_on_ct_end(point_nb_ct),
            reset_from_hard_soft_stop=True,
            stop_from_hard_stop=True,
        )
        card_o.set_counter_config(point_nb_ct, ct_config)
        extra_pulse = not_endless and ext_trig_readout
        acq_nb_points = self.acq_nb_points + (1 if extra_pulse else 0)
        card_o.set_counter_comparator_value(point_nb_ct, acq_nb_points)
        # gen. IRQ on point_nb (soft) stop, so acq_loop ends during stop_acq
        irq_counters.append(point_nb_ct)

        # make master enabled by software
        card_o.enable_counters_software((timer_ct, point_nb_ct))

        # ... and now for the slave channels

        channels = tuple(self.acq_channels)
        all_channels = channels + (timer_ct, point_nb_ct)

        integrator = dict([(ct, False) for ct in channels])
        # change the start and stop sources for the active channels
        for ch_nb in channels:
            ct_config = card_o.get_counter_config(ch_nb)
            ct_config["gate_source"] = ct_gate(gate_ct)
            ct_config["hard_start_source"] = start_on_ct_signal(timer_ct, "START")
            ct_config["hard_stop_source"] = stop_on_ct_stop(timer_ct)
            ct_config["reset_from_hard_soft_stop"] = not integrator[ch_nb]
            ct_config["stop_from_hard_stop"] = stop_from_hard_stop
            card_o.set_counter_config(ch_nb, ct_config)

        # if needed, configure the "output" counter
        if out_ct:
            start_signal = "START_STOP" if auto_restart else "START"
            out_start_source = start_on_ct_signal(timer_ct, start_signal)

            if ext_trig_readout:
                out_stop_source = stop_source(ext_rise_signal)
            elif out_cmp:
                out_stop_source = stop_on_ct_end(out_ct)
            elif self.__has_ext_exp():
                out_stop_source = stop_on_ct_end(in_ct)
            else:
                out_stop_source = stop_on_ct_stop(timer_ct)
            ct_config = card.CtConfig(
                clock_source=timer_clock_source,
                gate_source=ct_gate(timer_ct),
                hard_start_source=out_start_source,
                hard_stop_source=out_stop_source,
                reset_from_hard_soft_stop=True,
                stop_from_hard_stop=True,
            )
            card_o.set_counter_config(out_ct, ct_config)
            if out_cmp:
                card_o.set_counter_comparator_value(out_ct, out_cmp)
            card_o.enable_counters_software((out_ct,))

        # gate counter will latch all active counters at stop
        latch_sources = dict([(ct, gate_ct) for ct in all_channels])
        card_o.set_counters_latch_sources(latch_sources)

        # timer counter-to-latch signal will trigger DMA; at each DMA
        # trigger, all active counters (including timer and point_nb counters)
        # are stored to FIFO
        card_o.set_DMA_enable_trigger_latch((timer_ct,), all_channels)

        # dma transfer and error will also trigger DMA
        card_o.set_interrupts(
            counters=irq_counters, dma=True, error=True, fifo_half_full=True
        )

        # enable the active counters
        card_o.enable_counters_software(channels)

        # and finally the output channel
        if out_gate_ch:
            ch_source = card_o.get_output_channels_source()
            ch_source[out_gate_ch] = card.OutputSrc["CT_{0}_GATE".format(out_gate_ch)]
            card_o.set_output_channels_source(ch_source)
            filter_pol = card_o.get_output_channels_filter()
            filter_pol[out_gate_ch]["polarity_inverted"] = False
            card_o.set_output_channels_filter(filter_pol)

    def __get_counter_cmp(self):
        expo_time = (self.acq_expo_time or 0) * self.timer_freq
        point_period = (self.acq_point_period or 0) * self.timer_freq

        if not point_period and expo_time:
            # in zero-dead-time modes the output_counter counts one pulse less
            # so it can be restarted on timer end
            longer_timer = self.acq_mode in self.ZeroDeadTimeModes
            extra_gap = longer_timer and self.output_counter
            point_period = expo_time + (1 if extra_gap else 0)

        timer_cmp, out_cmp = None, None
        if self.__has_int_exp():
            timer_cmp = int(point_period)
            if self.output_counter:
                out_cmp = int(expo_time)

        return timer_cmp, out_cmp

    def __has_soft_start(self):
        return self.acq_mode in self.SoftStartModes

    def __has_int_trig(self):
        return self.acq_mode in self.IntTrigModes

    def __has_int_exp(self):
        return self.acq_mode in self.IntExpModes

    def __has_ext_start(self):
        return not self.__has_soft_start()

    def __has_ext_trig(self):
        return self.acq_mode in self.ExtTrigModes

    def __has_ext_exp(self):
        return self.acq_mode in self.ExtExpModes

    def __has_ext_sync(self):
        return self.__has_ext_start() or self.__has_ext_trig() or self.__has_ext_exp()

    def __in_ext_trig_readout(self):
        return self.acq_mode == AcqMode.ExtTrigReadout

    def prepare_acq(self):
        has_period = self.acq_point_period > 0
        mode_str = "int-trig-with-dead-time"
        if self.acq_mode in self.IntTrigDeadTimeModes:
            if not self.output_channel:
                raise ValueError("%s requires out_config" % mode_str)
            if not has_period:
                raise ValueError("%s must define acq. point period" % mode_str)
            elif self.acq_point_period <= self.acq_expo_time:
                raise ValueError("Acq. point period must be greater than expo.")
        elif has_period:
            raise ValueError("Acq. point period only allowed in %s" % mode_str)
        if self.__has_ext_sync() and not self.input_channel:
            raise ValueError("Must provide in_config in ext-trig modes")

        self.stop_acq()
        if self.acq_mode not in self.StdModes:
            raise NotImplementedError
        self.__buffer = []
        self.__last_point_nb = -1
        self.__last_error = None
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
            self._card.start_counters_software(counters)

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
        if self.output_counter:
            self._card.disable_counters_software((self.output_counter,))
        # this will generate point_nb_cnt STOP -> IRQ -> unblock acq_loop
        self._card.stop_counters_software(self._card.COUNTERS)

        gevent.wait([self.__event_loop])
        self.__event_loop = None
        self._send_status(self.__acq_status)

    def wait_acq(self):
        if self.__event_loop:
            gevent.wait([self.__event_loop])

    def trigger_latch(self, counters):
        self._card.trigger_counters_software_latch(counters)

    def trigger_point(self):
        if self.acq_status != AcqStatus.Running:
            raise ValueError("No acquisition is running")
        elif self.__has_soft_start() and not self.__soft_started:
            pass
        elif self.__has_int_trig():
            raise ValueError("Cannot trigger point in int-trig modes")

        counters = (self.internal_timer_counter,)
        restart = True
        if self.acq_mode == AcqMode.SoftTrigReadout:
            point_nb_ct = self.internal_point_nb_counter
            point_nb = self._card.get_counter_value(point_nb_ct)
            self._card.stop_counters_software(counters)
            start = not self.__soft_started
            restart = (
                start or self.is_endless_acq or (point_nb < self.acq_nb_points - 1)
            )
        elif self.acq_mode == AcqMode.IntTrigMulti:
            counters_status = self._card.get_counters_status()
            if counters_status[counters[0]]["run"]:
                raise RuntimeError("Counter still running")

        if self.__has_soft_start():
            self.__soft_started = True

        if restart:
            self._card.start_counters_software(counters)

    def dump_memory(self):
        return self._card.dump_memory()

    @property
    def acq_mode(self):
        return self.__acq_mode

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        if isinstance(acq_mode, str):
            acq_mode = AcqMode[acq_mode]
        else:
            acq_mode = AcqMode(acq_mode)
        self.__acq_mode = acq_mode

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
            raise ValueError("Invalid timer clock: %s" % timer_freq)
        if timer_freq > 12.5E6:
            self._log.warning(
                "The P201 has known bugs using frequencies "
                "above 12.5Mhz. Use it at your own risk"
            )
        self.__timer_freq = timer_freq

    @property
    def input_config(self):
        return self.__input_config

    @input_config.setter
    def input_config(self, config):
        config = config or {}
        channel = config.setdefault("channel", None)
        counter = config.setdefault("counter", channel)
        polarity = config.setdefault("polarity inverted", False)
        if channel is not None and channel not in self._card.INPUT_CHANNELS:
            raise ValueError("invalid input config channel %r", channel)
        if polarity not in (True, False):
            raise ValueError("invalid input config polarity inververted %r", polarity)
        self.__input_config = config

    @property
    def input_channel(self):
        return self.input_config["channel"]

    @input_channel.setter
    def input_channel(self, channel):
        trig = self.input_config
        trig["channel"] = channel
        trig["counter"] = channel
        self.input_config = trig

    @property
    def input_counter(self):
        return self.input_config["counter"]

    @property
    def output_config(self):
        return self.__output_config

    @output_config.setter
    def output_config(self, config):
        config = config or {}
        channel = config.setdefault("channel", None)
        counter = config.setdefault("counter", channel)
        mode = config.setdefault("mode", "gate")
        if channel is not None and channel not in self._card.OUTPUT_CHANNELS:
            raise ValueError("invalid output config channel %r", channel)
        if mode not in ("gate",):
            raise ValueError("invalid output mode %r", mode)
        self.__output_config = config

    @property
    def output_channel(self):
        return self.output_config["channel"]

    @output_channel.setter
    def output_channel(self, channel):
        trig = self.output_config
        trig["channel"] = channel
        trig["counter"] = channel
        self.output_config = trig

    @property
    def output_counter(self):
        return self.output_config["counter"]

    @property
    def counter_values(self):
        return self._card.get_counters_values()

    @property
    def latches(self):
        return self._card.get_latches_values()

    @property
    def last_point_nb(self):
        return self.__last_point_nb

    @property
    def last_error(self):
        return self.__last_error

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

    def get_data(self, from_index=None):
        if from_index is None:
            from_index = 0
        data = None
        with self.__buffer_lock:
            if self.__buffer:
                data = self.__buffer[from_index:]
        if data:
            return numpy.array(data, dtype=numpy.uint32)
        return numpy.array([[]], dtype=numpy.uint32)

    def configure(self, device_config):
        card_config = _build_card_config(device_config)
        card.configure_card(self._card, card_config)
        external = device_config.get("external sync", {})
        self.input_config = external.get("input", self.DefaultInputConfig)
        self.output_config = external.get("output", self.DefaultOutputConfig)

    @property
    def is_endless_acq(self):
        return self.acq_nb_points == 0


def __get_device_config(name):
    from bliss.config.static import get_config

    config = get_config()
    device_config = config.get_config(name)
    return device_config


def _build_card_config(device_config):
    card_config = dict(device_config)
    card_config["class"] = card_type = card_config.pop("type", "P201")
    card_class = card.get_ct2_card_class(card_type)
    out_ch = int(
        card_config.get("external sync", {}).get("output", {}).get("channel", -1)
    )
    for channel in card_config.get("channels", ()):
        address = int(channel["address"])
        level = channel.get("level", "TTL")
        ohm = channel.get("50 ohm", False)
        if address in card_class.INPUT_CHANNELS:
            input = channel.setdefault("input", {})
            input["level"] = level
            input["50 ohm"] = ohm
        if address in card_class.OUTPUT_CHANNELS:
            output = channel.setdefault("output", {})
            if address == out_ch:
                output["level"] = level
                input["level"] = "DISABLE"
            else:
                output["level"] = "DISABLE"

    return card_config


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    device = create_and_configure_device(node)
    return {name: device}, {name: device}


def create_and_configure_device(config_or_name):
    """
    Create a device from the given configuration (beacon compatible) or its
    configuration name.

    Args:
        config_or_name: (config or name: configuration dictionary (or
                        dictionary like object) or configuration name
    Returns:
        a new instance of :class:`CT2` configured and ready to go
    """
    if isinstance(config_or_name, str):
        device_config = __get_device_config(config_or_name)
        name = config_or_name
    else:
        device_config = config_or_name
        name = device_config["name"]

    card_config = _build_card_config(device_config)
    card_obj = card.create_and_configure_card(card_config)

    external = device_config.get("external sync", {})
    input_config = external.get("input", CT2.DefaultInputConfig)
    output_config = external.get("output", CT2.DefaultOutputConfig)
    device = CT2(card_obj)
    device.input_config = input_config
    device.output_config = output_config
    return device
