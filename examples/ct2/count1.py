"""
Simple example counting until a certain value on a counter
"""

from __future__ import print_function

import os
import sys
import pprint
import logging

import argparse

try:
    from bliss.controllers import ct2
except:
    this_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), os.path.pardir))
    sys.path.append(this_dir)
    from bliss.controllers import ct2

from bliss.controllers.ct2 import P201Card, Clock, Level, CtConfig, OutputSrc
from bliss.controllers.ct2 import CtClockSrc, CtGateSrc, CtHardStartSrc, CtHardStopSrc


def main():
    #logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log-level', type=str, default='info',
                        help='log level (debug, info, warning, error) [default: info]')
    parser.add_argument('--counter', type=int,
                        help='counter number', default=1)
    parser.add_argument('--value', type=int, default=1000*1000,
                        help='count until value')

    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    counter = args.counter
    value = args.value

    def out(msg):
        sys.stdout.write(msg)
        sys.stdout.flush()

    p201 = P201Card()
    p201.set_interrupts()
    p201.request_exclusive_access()
    p201.reset()
    p201.software_reset()

    # internal clock 100 Mhz
    p201.set_clock(Clock.CLK_100_MHz)

    # channel 10 output: counter 10 gate envelop
    p201.set_output_channels_level({counter: Level.TTL})

    # no 50 ohm adapter
    p201.set_input_channels_50ohm_adapter({})

    # channel 9 and 10: no filter, no polarity
    p201.set_output_channels_filter({})
    
    # channel N output: counter N gate envelop
    ct_N_gate = getattr(OutputSrc, "CT_%d_GATE" % counter)
    p201.set_output_channels_source({counter: ct_N_gate})

    # Internal clock to 1 Mhz [1us], Gate=1, Soft Start, HardStop on CMP,
    # Reset on Hard/SoftStop, Stop on HardStop
    hard_stop = getattr(CtHardStopSrc, "CT_{0}_EQ_CMP_{0}".format(counter))
    ct_config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                         gate_source=CtGateSrc.GATE_CMPT,
                         hard_start_source=CtHardStartSrc.SOFTWARE,
                         hard_stop_source=hard_stop,
                         reset_from_hard_soft_stop=True,
                         stop_from_hard_stop=True)
    p201.set_counter_config(counter, ct_config)

    # Latch N on Counter N HardStop
    p201.set_counters_latch_sources({counter: counter})

    # Counter N will count V/1000*1000 sec
    p201.set_counter_comparator_value(counter, value)

    started, start_count = False, 0
    while not started:
        # SoftStart on Counter N
        start_count += 1
        if start_count > 10:
            print("failed to start after 10 atempts" )
            break
        p201.set_counters_software_start_stop({counter: True})
        status = p201.get_counters_status()
        started = status[counter].run

    if start_count > 1:
        logging.warning("took %d times to start", start_count)

    if started:
        print("Started!")
        import time
        while True:
            time.sleep(0.1)
            counter_value = p201.get_counter_value(counter)
            latch_value = p201.get_latch_value(counter)
            status = p201.get_counters_status()
            if not status[counter].run:
                break
            msg = "\r%07d %07d" % (counter_value, latch_value)
            out(msg)
        print("\n%07d %07d" % (counter_value, latch_value))

    p201.disable_counters_software((counter,))

    pprint.pprint(p201.get_counters_status())
    p201.relinquish_exclusive_access()

    return p201


if __name__ == "__main__":
    main()
