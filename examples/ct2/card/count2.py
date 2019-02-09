"""
Simple example counting n counters to a certain value.
Each counter is configured with a different clock
"""


import os
import sys
import time
import pprint
import logging
import argparse

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


def out(msg=""):
    sys.stdout.write(msg)
    sys.stdout.flush()


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        help="log level (debug, info, warning, error) [default: info]",
    )
    parser.add_argument(
        "--value", type=int, default=1000 * 1000, help="count until value"
    )
    parser.add_argument(
        "--nb_counters", type=int, default=6, help="use first n counters (max=6)"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    value = args.value
    nb_counters = args.nb_counters

    if nb_counters > 6:
        print("Can only use first 6 counters")
        sys.exit(1)

    counters = tuple(range(1, nb_counters + 1))

    card = P201Card()
    card.request_exclusive_access()
    card.reset()
    card.software_reset()

    # internal clock 100 Mhz
    card.set_clock(Clock.CLK_100_MHz)

    for counter in counters:
        hard_stop = getattr(CtHardStopSrc, "CT_{0}_EQ_CMP_{0}".format(counter))
        ct_config = CtConfig(
            clock_source=CtClockSrc(counter - 1),
            gate_source=CtGateSrc.GATE_CMPT,
            hard_start_source=CtHardStartSrc.SOFTWARE,
            hard_stop_source=hard_stop,
            reset_from_hard_soft_stop=True,
            stop_from_hard_stop=True,
        )

        card.set_counter_config(counter, ct_config)
        card.set_counter_comparator_value(counter, value)

    # Latch N on Counter N HardStop
    card.set_counters_latch_sources(
        dict([(counter, (counter,)) for counter in counters])
    )
    card.enable_counters_software(counters)

    # Start!
    card.start_counters_software(counters)

    print("Started!")
    while True:
        time.sleep(0.1)
        counters_values = card.get_counters_values()[:nb_counters]
        latches_values = card.get_latches_values()[:nb_counters]
        run = False
        for ct_status in list(card.get_counters_status().values()):
            run = run or ct_status["run"]
        if not run:
            break
        out("\r{0} {1}".format(counters_values.tolist(), latches_values.tolist()))
    print("\n{0} {1}".format(counters_values.tolist(), latches_values.tolist()))

    pprint.pprint(card.get_counters_status())
    card.disable_counters_software((counter,))
    card.relinquish_exclusive_access()

    return card


if __name__ == "__main__":
    main()
