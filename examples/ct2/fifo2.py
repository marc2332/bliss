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

from bliss.controllers.ct2 import P201, Clock, Level, CtConfig, OutputSrc
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

    hard_start = getattr(CtHardStartSrc, "CT_{0}_START".format(counter))
    ct_11_config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                            gate_source=CtGateSrc.GATE_CMPT,
                            hard_start_source=hard_start,
                            hard_stop_source=CtHardStopSrc.SOFTWARE,
                            reset_from_hard_soft_stop=False,
                            stop_from_hard_stop=False)

    clock_source = getattr(CtClockSrc, "INC_CT_{0}_STOP".format(counter))
    ct_12_config = CtConfig(clock_source=clock_source,
                            gate_source=CtGateSrc.GATE_CMPT,
                            hard_start_source=hard_start,
                            hard_stop_source=CtHardStopSrc.SOFTWARE,
                            reset_from_hard_soft_stop=False,
                            stop_from_hard_stop=False)

    card.set_counters_config({counter: ct_config, 11:ct_11_config, 12:ct_12_config})

    card.set_counter_comparator_value(counter, value)
    
    # Latch N on Counter N HardStop
#    card.set_counters_latch_sources({counter: [counter], 10 : [counter]})
    card.set_counters_latch_sources({counter: [counter], 11: [counter], 12: [counter]})

    # counter *counter* to latch triggers DMA
    # at each DMA trigger, counters *counter*, 11 and 12 are stored to FIFO
    card.set_DMA_enable_trigger_latch({counter:True}, {counter:True, 11: True, 12: True})

    card.set_interrupts(dma=True, error=True)

    card.set_counters_software_enable({counter: True})
    
    # force creation of a FIFO interface
    fifo = card.fifo

    etl = card.get_DMA_enable_trigger_latch()
    nb_counters = etl[1].values().count(True)

    def read_fifo(self, nb_events=0):
        fifo_status = self.get_FIFO_status()
        max_events = fifo_status.size / nb_counters
        if not nb_events or nb_events > max_events:
            nb_events = max_events
        buff = self.fifo[:nb_events * nb_counters * ct2.CT2_REG_SIZE]
        return numpy.ndarray((nb_events, nb_counters), dtype=numpy.uint32, buffer=buff), fifo_status

    card.__class__.read_fifo = read_fifo

    nsec = 10
    card._fifo_stat = numpy.zeros((nsec*1000000/value,), dtype='uint32')
    card._fifo_stat_index = 0


def main():

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--log-level', type=str, default='info',
                        help='log level (debug, info, warning, error) [default: info]')
    parser.add_argument('--counter', type=int,
                        help='counter number', default=1)
    parser.add_argument('--value', type=int, default=1000*1000,
                        help='count until value')

    args = parser.parse_args()
    
    counter = args.counter
    value = args.value

    if counter > 9:
        print("Can only use counters 1 to 9")
        sys.exit()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    p201 = P201()
    p201.request_exclusive_access()
    p201.disable_interrupts()
    p201.reset()
    p201.software_reset()
    p201.reset_FIFO_error_flags()
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
    except:
        sys.excepthook(*sys.exc_info())
    finally:
        print ("Clean up!")
        p201.disable_interrupts()
        p201.reset()
        p201.software_reset()


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

    fifo, fifo_status = card.read_fifo()

    if dma:
        d = card._fifo_stat
        if card._fifo_stat_index == d.shape[0]:
            print("Statistics nb_zeros %d;" % (d == numpy.zeros(d.shape, dtype=d.dtype)).sum())
            print("Statistics", d.min(), d.max(), d.mean(), d.std())
            return 1, True
        d[card._fifo_stat_index] = len(fifo)
        card._fifo_stat_index += 1

        logging.info("event")
        print(fifo)
        print(card.get_counter_value(11),card.get_latch_value(11))

        if len(fifo) == 0:
            print("Empty FIFO!")
            #raise ct2.CT2Exception("Empty FIFO after DMA event")
        #print("received latch-FIFO transfer success notice!")
    else:
        print("Non DMA interrupt")

    if fifo_half_full:
        print("received FIFO half full notice (%d)" % fifo_status.size)

    if error:
        print("error: received latch-FIFO transfer error notice")

    if fifo_status.full:
        print("warning: full FIFO!")
    if fifo_status.overrun_error:
        print("warning: FIFO overrun error")
    if fifo_status.read_error:
        print("warning: FIFO read error")
    if fifo_status.write_error:
        print("warning: FIFO write error")
#    if not (fifo_status.size % 10):
#        print("FIFO filled up to: %d" % fifo_status.size)

    return 0, True


if __name__ == "__main__":
    main()
