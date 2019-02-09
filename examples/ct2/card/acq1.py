"""
ESRF-BCU acquisition with internal master:
counter 11 counts the acquisition time (using internal clock);
counter 12 counts the number of points
"""

import os
import sys
import time
import pprint
import logging
import argparse
import datetime

import numpy

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


def configure(device, channels):
    device.request_exclusive_access()
    device.set_interrupts()
    device.reset()
    device.software_reset()

    # -------------------------------------------------------------------------
    # Channel configuration (could be loaded from beacon, for example. We
    # choose to hard code it here)
    # -------------------------------------------------------------------------

    # for counters we only care about clock source, gate source here. The rest
    # will be up to the actual acquisition to setup according to the type of
    # acquisition
    for _, ch_nb in list(channels.items()):
        ct_config = CtConfig(
            clock_source=CtClockSrc(ch_nb % 5),
            gate_source=CtGateSrc.GATE_CMPT,
            # anything will do for the remaining fields. It
            # will be properly setup in the acquisition slave
            # setup
            hard_start_source=CtHardStartSrc.SOFTWARE,
            hard_stop_source=CtHardStopSrc.SOFTWARE,
            reset_from_hard_soft_stop=False,
            stop_from_hard_stop=False,
        )
        device.set_counter_config(ch_nb, ct_config)

    # TODO: Set input and output channel configuration (TTL/NIM level, 50ohm,
    # edge interrupt, etc)

    # internal clock 100 Mhz
    device.set_clock(Clock.CLK_100_MHz)


def prepare_master(device, acq_time, nb_points):
    ct_11_config = CtConfig(
        clock_source=CtClockSrc.CLK_100_MHz,
        gate_source=CtGateSrc.CT_12_GATE_ENVELOP,
        hard_start_source=CtHardStartSrc.SOFTWARE,
        hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11,
        reset_from_hard_soft_stop=True,
        stop_from_hard_stop=False,
    )
    ct_12_config = CtConfig(
        clock_source=CtClockSrc.INC_CT_11_STOP,
        gate_source=CtGateSrc.GATE_CMPT,
        hard_start_source=CtHardStartSrc.SOFTWARE,
        hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,
        reset_from_hard_soft_stop=True,
        stop_from_hard_stop=True,
    )

    device.set_counters_config({11: ct_11_config, 12: ct_12_config})
    device.set_counter_comparator_value(11, int(acq_time * 1E8))
    device.set_counter_comparator_value(12, nb_points)


def prepare_slaves(device, acq_time, nb_points, channels):
    channel_nbs = list(channels.values())
    for ch_name, ch_nb in channels.items():
        ct_config = device.get_counter_config(ch_nb)
        ct_config["gate_source"] = CtGateSrc.CT_11_GATE_ENVELOP
        ct_config["hard_start_source"] = CtHardStartSrc.SOFTWARE
        ct_config["hard_stop_source"] = CtHardStopSrc.CT_11_EQ_CMP_11
        ct_config["reset_from_hard_soft_stop"] = True
        ct_config["stop_from_hard_stop"] = False
        device.set_counter_config(ch_nb, ct_config)
        device.set_counter_config(ch_nb, ct_config)

    # counter 11 will latch all active counters/channels
    latch_sources = dict([(ct, 11) for ct in channel_nbs + [12]])
    device.set_counters_latch_sources(latch_sources)

    # make all counters enabled by software
    device.enable_counters_software(channel_nbs + [11, 12])


def main():
    def to_str(values, fmt="9d"):
        fmt = "%" + fmt
        return "[" + "".join([fmt % value for value in values]) + "]"

    def out(msg=""):
        sys.stdout.write(msg)
        sys.stdout.flush()

    channels = {"I0": 3, "V2F": 5, "SCA": 6}

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        help="log level (debug, info, warning, error) [default: info]",
    )
    parser.add_argument("--nb-points", type=int, help="number of points", default=10)
    parser.add_argument("--acq-time", type=float, default=1, help="acquisition time")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    nb_points = args.nb_points
    acq_time = args.acq_time

    device = P201Card()

    configure(device, channels)

    prepare_master(device, acq_time, nb_points)
    prepare_slaves(device, acq_time, nb_points, channels)

    # start counting...
    nap = 0.1
    start_time = time.time()

    device.start_counters_software(list(channels.values()) + [11, 12])

    while True:
        time.sleep(nap)
        counter_values = device.get_counters_values()
        latch_values = device.get_latches_values()
        status = device.get_counters_status()
        if not status[12]["run"]:
            stop_time = time.time()
            break
        msg = "\r{0} {1}".format(to_str(counter_values), to_str(latch_values))
        out(msg)
    print(("\n{0} {1}".format(to_str(counter_values), to_str(latch_values))))
    print(("Took ~{0}s (err: {1}s)".format(stop_time - start_time, nap)))
    pprint.pprint(device.get_counters_status())

    device.relinquish_exclusive_access()


if __name__ == "__main__":
    main()
