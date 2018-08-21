"""
Simple example counting until a certain value on all counters
"""

from __future__ import print_function

import os
import sys
import pprint

import argparse

from bliss.controllers.ct2.card import (
    P201Card,
    Clock,
    Level,
    CtConfig,
    OutputSrc,
    CtClockSrc,
    CtGateSrc,
    CtHardStartSrc,
    CtHardStopSrc,
)


def main():
    # logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument(
        "--value", type=int, default=1000 * 1000, help="count until value"
    )

    args = parser.parse_args()
    value = args.value

    def out(msg):
        sys.stdout.write(msg)
        sys.stdout.flush()

    p201 = P201Card()
    p201.request_exclusive_access()
    p201.reset()
    p201.software_reset()

    # internal clock 100 Mhz
    p201.set_clock(Clock.CLK_100_MHz)

    # channel 10 output: counter 10 gate envelop
    p201.set_output_channels_level(dict([(ct, Level.TTL) for ct in p201.COUNTERS]))

    # no 50 ohm adapter
    p201.set_input_channels_50ohm_adapter({})

    # channel 9 and 10: no filter, no polarity
    p201.set_output_channels_filter({})

    # channel N output: counter N gate envelop
    gate = dict([(ct, getattr(OutputSrc, "CT_%d_GATE" % ct)) for ct in p201.COUNTERS])
    p201.set_output_channels_source(gate)

    # Internal clock to 1 Mhz [1us], Gate=1, Soft Start, HardStop on CMP,
    # Reset on Hard/SoftStop, Stop on HardStop
    cts_cfg = {}
    for counter in p201.COUNTERS:
        hard_stop = getattr(CtHardStopSrc, "CT_{0}_EQ_CMP_{0}".format(counter))
        cfg = CtConfig(
            clock_source=CtClockSrc.CLK_1_MHz,
            gate_source=CtGateSrc.GATE_CMPT,
            hard_start_source=CtHardStartSrc.SOFTWARE,
            hard_stop_source=hard_stop,
            reset_from_hard_soft_stop=True,
            stop_from_hard_stop=True,
        )
        cts_cfg[counter] = cfg
    p201.set_counters_config(cts_cfg)

    # Latch N on Counter N HardStop
    p201.set_counters_latch_sources(dict([(c, c) for c in p201.COUNTERS]))

    # Counter N will count V/1000*1000 sec
    for counter in p201.COUNTERS:
        p201.set_counter_comparator_value(counter, value)

    started, start_count = False, 0
    while not started:
        # SoftStart on Counter N
        start_count += 1
        if start_count > 10:
            print("failed to start after 10 atempts")
            break
        p201.set_counters_software_start_stop(dict([(c, True) for c in p201.COUNTERS]))
        status = p201.get_counters_status()
        started = status[1]["run"]

    if start_count > 1:
        logging.warning("took %d times to start", start_count)

    if started:
        print("Started!")
        import time

        while True:
            time.sleep(0.1)
            counter_values = p201.get_counters_values()
            latch_values = p201.get_latches_values()
            status = p201.get_counters_status()
            if not status[counter]["run"]:
                break
            msg = "\r{0} {1}".format(counter_values.tolist(), latch_values.tolist())
            out(msg)
        print("\n{0} {1}".format(counter_values.tolist(), latch_values.tolist()))

    pprint.pprint(p201.get_counters_status())
    p201.relinquish_exclusive_access()

    return p201


if __name__ == "__main__":
    main()
