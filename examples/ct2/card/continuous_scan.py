# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Example
"""

from __future__ import print_function

import os
import sys
import pprint
import logging
import argparse
import select
from select import epoll


from bliss.controllers.ct2.card import (
    P201Card,
    Clock,
    Level,
    CtConfig,
    OutputSrc,
    FilterOutput,
    FilterClock,
    FilterInput,
    FilterInputSelection,
    CtClockSrc,
    CtGateSrc,
    CtHardStartSrc,
    CtHardStopSrc,
)

# s_si  ... scan initiation signal
# s_en  ... encoder signal
# s_t_1 ... detector 1 signal
# s_t_2 ... detector 2 signal
# c_so  ... scan origin/ramp-up/start counter
# c_i   ... displacement interval counter
# c_d   ... displacement interval size counter
# c_t_1 ... detector 1 pulse counter
# c_t_2 ... detector 2 pulse counter

# 1 kHz on s_en with d = 2000 makes for 2 seconds long displacement
# intervals.  With an f_0 of 20 MHz, and 20 MHz ÷ 10000, we obtain
# 2 kHz s_t_1 impulse rate which results in (roughly) 4000 counts
# for c_t_1 per interval.  A 20 MHz ÷ 80000 makes for 250 Hz s_t_2
# impulse rate which results in (roughly) 500 counts for c_t_2 per
# interval.

n_so = 4000  # scan origin count
n_e = 44000  # end count
i = 20  # displacement interval count
d = 2000  # displacement interval size

# counters:
c_so = 1
c_i = 11
c_d = 12
c_t_1 = 2
c_t_2 = 3


def out(msg):
    sys.stdout.write(msg)
    sys.stdout.flush()


def main():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Process some integers.")

    p201 = P201Card()
    try:
        go(p201)
    except KeyboardInterrupt:
        print("\nCtrl-C: Bailing out")
    finally:
        clean_up(p201)


def go(card):

    n_so = 4000  # scan origin count
    n_e = 44000  # end count
    i = 20  # displacement interval count
    d = 2000  # displacement interval size

    # counters:
    c_so = 1
    c_i = 11
    c_d = 12
    c_t_1 = 2
    c_t_2 = 3

    counter_interrupts = {}
    latch_sources = {}

    card.request_exclusive_access()
    card.reset()
    card.software_reset()

    # internal clock 40 Mhz
    card.set_clock(Clock.CLK_40_MHz)

    # Make sure the counters are disabled (soft_enable_disable).
    card.disable_counters_software(card.COUNTERS)

    # Configure counter 1 aka c_so:
    # (1) clock source is s_en
    # (2) gate wide open
    # (3) started by s_si
    # (4) halted by ccl 1/egal ...
    # (5) ... while keeping its value ...
    config = CtConfig(
        clock_source=CtClockSrc.CH_1_RISING_EDGE,  # (1)
        gate_source=CtGateSrc.GATE_CMPT,  # (2)
        hard_start_source=CtHardStartSrc.CH_2_RISING_EDGE,  # (3)
        hard_stop_source=CtHardStopSrc.CT_1_EQ_CMP_1,  # (4)
        reset_from_hard_soft_stop=False,  # (5)
        stop_from_hard_stop=True,
    )  # (4)
    card.set_counter_config(c_so, config)

    card.set_counter_comparator_value(c_so, n_so)

    # ... and signaling its end to the outside world.
    counter_interrupts[c_so] = True

    # Configure counter 11 aka c_i:
    # (1) clock source is ccl 12/end aka c_d/end
    # (2) gate wide open
    # (3) started by ccl 1/end aka c_so/end
    # (4) halted by ccl 11/egal ...
    # (5) ... while keeping its value ...
    config = CtConfig(
        clock_source=CtClockSrc.INC_CT_12_STOP,  # (1)
        gate_source=CtGateSrc.GATE_CMPT,  # (2)
        hard_start_source=CtHardStartSrc.CT_1_STOP,  # (3)
        hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11,  # (4)
        reset_from_hard_soft_stop=False,  # (5)
        stop_from_hard_stop=True,
    )  # (4)
    card.set_counter_config(c_i, config)

    card.set_counter_comparator_value(c_i, i)

    # ... and signaling its end to the outside world.
    counter_interrupts[c_i] = True

    # Configure counter 12 aka c_d:
    # (1) clock source is s_en
    # (2) gate wide open
    # (3) started by ccl 1/end aka c_so/end
    # (4) reset by ccl 12/egal ...
    # (5) ... while running continuously ...
    config = CtConfig(
        clock_source=CtClockSrc.CH_1_RISING_EDGE,  # (1)
        gate_source=CtGateSrc.GATE_CMPT,  # (2)
        hard_start_source=CtHardStartSrc.CT_1_STOP,  # (3)
        hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,  # (4)
        reset_from_hard_soft_stop=True,  # (5)
        stop_from_hard_stop=False,
    )  # (4)
    card.set_counter_config(c_d, config)

    card.set_counter_comparator_value(c_d, d)

    # ... and having us tell when it wraps.
    counter_interrupts[c_d] = True

    # Configure counter 2 aka c_t_1:
    # (1) clock source is s_t_1
    # (2) gate wide open
    # (3) started by ccl 1/end aka c_so/end
    # (4) reset by ccl 12/egal aka c_d/egal
    # (5) ... while running continuously
    config = CtConfig(
        clock_source=CtClockSrc.CLK_10_KHz,  # (1)
        gate_source=CtGateSrc.GATE_CMPT,  # (2)
        hard_start_source=CtHardStartSrc.CT_1_STOP,  # (3)
        hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,  # (4)
        reset_from_hard_soft_stop=True,  # (5)
        stop_from_hard_stop=False,
    )  # (4)
    card.set_counter_config(c_t_1, config)

    # The latch signal shall be generated from ccl 12/stop + disable
    # aka c_d/stop + disable, so that we're latching all from the same
    # source and before actually clearing the counter.
    latch_sources[c_t_1] = [c_d]

    # Configure counter 3 aka c_t_2:
    # (1) clock source is s_t_2
    # (2) gate wide open
    # (3) started by ccl 1/end aka c_so/end
    # (4) reset by ccl 12/egal aka c_d/egal
    # (5) ... while running continuously
    config = CtConfig(
        clock_source=CtClockSrc.CLK_1_25_KHz,  # (1)
        gate_source=CtGateSrc.GATE_CMPT,  # (2)
        hard_start_source=CtHardStartSrc.CT_1_STOP,  # (3)
        hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,  # (4)
        reset_from_hard_soft_stop=True,  # (5)
        stop_from_hard_stop=False,
    )  # (4)
    card.set_counter_config(c_t_2, config)

    latch_sources[c_t_2] = [c_d]

    # write all latch sources
    card.set_counters_latch_sources(latch_sources)

    # We store the latched counter values of ccls 2 and 3 (2)
    # while it should suffice that the transfer is triggered by
    # c_t_1's latch (1).  But first and foremost, we enable the
    # transfer (3).
    card.set_DMA_enable_trigger_latch({c_t_1: True}, {c_t_1: True, c_t_2: True})

    # Set output cell 1's signal source to ic 1 (1) and
    # output cell 2's signal source to ic 2(2).
    card.set_output_channels_source({9: OutputSrc.CH_1_INPUT, 10: OutputSrc.CH_2_INPUT})

    # Set the filter configuration for both outputs.  Neither cell's signal
    # shall be inverted nor filters used
    card.set_output_channels_filter(
        {
            9: FilterOutput(polarity=0, enable=False, clock=FilterClock.CLK_100_MHz),
            10: FilterOutput(polarity=0, enable=False, clock=FilterClock.CLK_100_MHz),
        }
    )

    # Set both output cells' levels to TTL.
    card.set_output_channels_level({9: Level.TTL, 10: Level.TTL})

    # Enable input termination on all inputs except ic 9 and ic10.
    card.set_input_channels_50ohm_adapter(dict([(i, True) for i in range(1, 9)]))

    # Set input cells 1's (1) and 2's (2) filter configuration
    # to short pulse capture.
    card.set_input_channels_filter(
        {
            1: FilterInput(
                clock=FilterClock.CLK_100_MHz,
                selection=FilterInputSelection.SINGLE_SHORT_PULSE_CAPTURE,
            ),
            2: FilterInput(
                clock=FilterClock.CLK_100_MHz,
                selection=FilterInputSelection.SINGLE_SHORT_PULSE_CAPTURE,
            ),
        }
    )

    card.set_input_channels_level({1: Level.TTL, 2: Level.TTL})

    fifo = card.fifo

    poll = epoll()
    poll.register(card, select.EPOLLIN | select.EPOLLHUP | select.EPOLLERR)

    card.set_interrupts(
        counters=counter_interrupts, dma=True, fifo_half_full=True, error=True
    )

    # enable counters
    card.enable_counters_software([1, 11, 12, 2, 3])

    stop, finish = False, False
    while not stop:
        events = poll.poll(timeout=1)
        if not events:
            logging.debug("poll loop")
            continue
        for fd, event in events:
            result = handle_event(card, fifo, fd, event)
            if result == 0:
                continue
            elif result == 1:
                stop = finish = True
                break
            elif result in (2, 3):
                stop = True
                break
            else:
                stop = True
                break


def handle_event(card, fifo, fd, event):
    if event & (select.EPOLLHUP):
        print("epoll hang up event on {0}, bailing out".format(fd))
        return 2
    elif event & (select.EPOLLERR):
        print("epoll error event on {0}, bailing out".format(fd))
        return 3

    print("epoll event {0} on {1}".format(event, fd))
    (
        counters,
        channels,
        dma,
        fifo_half_full,
        error,
    ), tstamp = card.acknowledge_interrupt()

    if counters[c_so]:
        print("c_so/end asserted, we have begun!")

    if counters[c_d]:
        print("c_d/end asserted")

    if dma:
        print("received latch-FIFO transfer success notice")

    if fifo_half_full:
        print("received FIFO half full notice")

    if error:
        print("received latch-FIFO transfer error notice")

    fifo_status = card.get_FIFO_status()

    for i in range(fifo_status.size):
        print("FIFO[%d] = %d" % (i, fifo[i]))

    if counters[c_i]:
        print("c_i/end asserted, we're done here")
        return 1

    return 0


def clean_up(card):
    card.set_interrupts()
    card.disable_counters_software(card.COUNTERS)


if __name__ == "__main__":
    main()
