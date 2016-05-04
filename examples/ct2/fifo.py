"""
Simple example counting 
"""

from __future__ import print_function

import os
import sys
import pprint
import select
import logging
import argparse
import datetime

import numpy

try:
    from bliss.controllers import ct2
except:
    this_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), os.path.pardir))
    sys.path.append(this_dir)
    from bliss.controllers import ct2

from bliss.controllers.ct2 import P201Card, Clock, Level, CtConfig, OutputSrc
from bliss.controllers.ct2 import CtClockSrc, CtGateSrc, CtHardStartSrc, CtHardStopSrc


def out(msg=""):
    sys.stdout.write(msg)
    sys.stdout.flush()


def prepare(card, counter, value):

    # internal clock 100 Mhz
    card.set_clock(Clock.CLK_100_MHz)

    hard_stop = getattr(CtHardStopSrc, "CT_{0}_EQ_CMP_{0}".format(counter))
    ct_config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                         gate_source=CtGateSrc.GATE_CMPT,
                         hard_start_source=CtHardStartSrc.SOFTWARE,
                         hard_stop_source=hard_stop,
                         reset_from_hard_soft_stop=True,
                         stop_from_hard_stop=False)

    card.set_counter_config(counter, ct_config)
    
    card.set_counter_comparator_value(counter, value)
    
    # Latch N on Counter N HardStop
    card.set_counters_latch_sources({counter: counter})

    card.set_counter_comparator_value(counter, value)

    card.set_DMA_enable_trigger_latch({1:True}, {1:True})

    card.set_interrupts(counters={counter: True},
                        dma=True, fifo_half_full=True, error=True)

    card.enable_counters_software([1])
    
    card._fifo = card.fifo

    card._interrupt_delay_stats = []


def main():

    parser = argparse.ArgumentParser(description='Process some integers.')
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

    p201 = P201Card()
    p201.request_exclusive_access()
    p201.disable_interrupts()
    p201.reset()
    p201.software_reset()
    p201.enable_interrupts(100)

    poll = select.epoll()
    poll.register(p201, select.EPOLLIN | select.EPOLLHUP | select.EPOLLERR)
    poll.register(sys.stdin, select.EPOLLIN)

    stop = False
    loop = 0
    out("Ready to accept commands (start, stop, Ctrl-D to abort!\n> ")
    try:
        while not stop:
            loop += 1
            events = poll.poll()
            for fd, event in events:
                if fd == sys.stdin.fileno():
                    handle = handle_cmd
                elif fd == p201.fileno():
                    handle = handle_card
                result, cont = handle(p201, counter, value, fd, event)
                if result:
                    stop = True
                    break
                else:
                    if not cont:
                        out("> ")
                        
    except KeyboardInterrupt:
        print("\rCtrl-C pressed. Bailing out!")
    finally:
        print ("Clean up!")
        p201.disable_interrupts()
        p201.reset()
        p201.software_reset()

    stats = numpy.array(p201._interrupt_delay_stats)
    avg = numpy.average(stats)
    mi, ma = numpy.min(stats), numpy.max(stats)
    print("Interrupt delay stats:")
    print("nb samples: %d, avg: %.3f us, min: %.3f us, max: %.3f us" % \
              (len(stats), avg, mi, ma))


def handle_cmd(card, counter, value, fd, event):
    cmd = os.read(fd, 1024)
    if not cmd:
        print("\rCtrl-D pressed. Bailing out!")
        return 1, False
    cmd = cmd[:-1]
    if not cmd:
        return 0, False
    if cmd == 'start':
        print("Software start!")
        prepare(card, counter, value)
        card.set_counters_software_start_stop({counter: True})
        return 0, True
    elif cmd == 'stop':
        return 0, False
    else:
        try:
            eval(cmd)
        except:
            sys.excepthook(*sys.exc_info())
        print()
        return 0, False
    return 3, False

def handle_card(card, counter, value, fd, event):
    t = ct2.time.monotonic_raw()
    if event & (select.EPOLLHUP):
        print("error: epoll hang up event on {0}, bailing out".format(fd))
        return 2, False
    elif event & (select.EPOLLERR):
        print("error: epoll error event on {0}, bailing out".format(fd))
        return 3, False

    (counters, channels, dma, fifo_half_full, error), tstamp = \
        card.acknowledge_interrupt()
    dt_us = (t - tstamp) * 1E6
    card._interrupt_delay_stats.append(dt_us)
    print ("epoll event {0} on {1} (delay={2:.3f} us)".format(event, fd, dt_us))

    if dma:
        print("received latch-FIFO transfer success notice!")

    if fifo_half_full:
        print("received FIFO half full notice")

    if error:
        print("error: received latch-FIFO transfer error notice")

    fifo_status = card.get_FIFO_status()
    if fifo_status.full:
        print("warning: full FIFO!")
    if fifo_status.overrun_error:
        print("warning: FIFO overrun error")
    if fifo_status.read_error:
        print("warning: FIFO read error")
    if fifo_status.write_error:
        print("warning: FIFO write error")
    if not (fifo_status.size % 10):
        print("FIFO filled up to: %d" % fifo_status.size)
        print("FIFO: %s" % card._fifo)

    return 0, True


if __name__ == "__main__":
    main()
