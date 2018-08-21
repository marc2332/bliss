"""
ESRF-BCU acquisition with internal master:
counter 11 counts the acquisition time (using internal clock);
counter 12 counts the number of points. Reading from FIFO!
"""

import os
import sys
import time
import logging
import argparse

import numpy

try:
    from gevent.select import select
except ImportError:
    from select import select


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
    device.reset_FIFO_error_flags()

    # -------------------------------------------------------------------------
    # Channel configuration (could be loaded from beacon, for example. We
    # choose to hard code it here)
    # -------------------------------------------------------------------------

    # for counters we only care about clock source, gate source here. The rest
    # will be up to the actual acquisition to setup according to the type of
    # acquisition
    for _, ch_nb in channels.items():
        ct_config = CtConfig(
            clock_source=CtClockSrc(ch_nb % 5),
            # anything will do for the remaining fields. It
            # will be properly setup in the acquisition slave
            # setup
            gate_source=CtGateSrc.CT_11_GATE_ENVELOP,
            hard_start_source=CtHardStartSrc.SOFTWARE,
            hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,
            reset_from_hard_soft_stop=True,
            stop_from_hard_stop=True,
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
        hard_start_source=CtHardStartSrc.CT_12_START,
        hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11,
        reset_from_hard_soft_stop=True,
        stop_from_hard_stop=False,
    )
    device.set_counter_config(11, ct_11_config)

    ct_12_config = CtConfig(
        clock_source=CtClockSrc.INC_CT_11_STOP,
        gate_source=CtGateSrc.GATE_CMPT,
        hard_start_source=CtHardStartSrc.SOFTWARE,
        hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,
        reset_from_hard_soft_stop=True,
        stop_from_hard_stop=True,
    )
    device.set_counter_config(12, ct_12_config)

    device.set_counter_comparator_value(11, int(acq_time * 1E8))
    device.set_counter_comparator_value(12, nb_points)

    # dma transfer and error will trigger DMA
    # also counter 12 stop should trigger an interrupt (this way we know that the
    # acquisition has finished without having to query the counter 12 status)
    device.set_interrupts(counters=(12,), dma=True, error=True)

    # make master enabled by software
    device.enable_counters_software([11, 12])


def prepare_slaves(device, acq_time, nb_points, channels, accumulate=False):
    channel_nbs = list(channels.values())

    if accumulate:
        hard_stop = CtHardStopSrc.SOFTWARE
    else:
        hard_stop = CtHardStopSrc.CT_11_EQ_CMP_11

    for ch_name, ch_nb in channels.iteritems():
        ct_config = device.get_counter_config(ch_nb)
        ct_config = CtConfig(
            clock_source=ct_config["clock_source"],
            gate_source=CtGateSrc.CT_12_GATE_ENVELOP,
            hard_start_source=CtHardStartSrc.CT_12_START,
            hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11,
            reset_from_hard_soft_stop=True,
            stop_from_hard_stop=False,
        )
        device.set_counter_config(ch_nb, ct_config)

    # counter 11 will latch all active counters/channels
    latch_sources = dict([(ct, 11) for ct in channel_nbs + [11, 12]])
    device.set_counters_latch_sources(latch_sources)

    # one of the active counter-to-latch signal will trigger DMA; at each DMA
    # trigger, all active counters (+ counter 12) are stored to FIFO
    # (counter 11 cannot be the one to trigger because it is not being latched)
    device.set_DMA_enable_trigger_latch((11,), channel_nbs + [11, 12])

    device.enable_counters_software(channel_nbs)


def main():
    def to_str(values, fmt="9d"):
        fmt = "%" + fmt
        return "[" + "".join([fmt % value for value in values]) + "]"

    def out(msg=""):
        sys.stdout.write(msg)
        sys.stdout.flush()

    channels = {"I0": 1, "V2F": 5, "SCA": 7, "SCA2": 8}

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        help="log level (debug, info, warning, error) [default: info]",
    )
    parser.add_argument("--nb-points", type=int, help="number of points", default=10)
    parser.add_argument("--acq-time", type=float, default=1, help="acquisition time")
    parser.add_argument("--nb-acq", type=int, default=1, help="number of acquisitions")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    nb_points = args.nb_points
    acq_time = args.acq_time
    nb_acq = args.nb_acq

    device = P201Card()

    configure(device, channels)
    prepare_master(device, acq_time, nb_points)
    prepare_slaves(device, acq_time, nb_points, channels, accumulate=False)

    loop = 0
    try:
        while loop < nb_acq:
            print("Acquisition #{0}".format(loop))
            go(device, channels)
            loop += 1
    except KeyboardInterrupt:
        print("\rCtrl-C pressed. Bailing out!")
    except:
        sys.excepthook(*sys.exc_info())
    finally:
        print("Clean up!")
        device.set_interrupts()
        device.reset()
        device.software_reset()
        device.relinquish_exclusive_access()


def go(device, channels):
    channelid2name = [(nb, name) for name, nb in channels.iteritems()]
    channelid2name += [(11, "integ_time"), (12, "point_nb")]

    start_time = time.time()

    # start counting...
    # slaves start all
    device.start_counters_software(channels.values())

    # master start all
    device.start_counters_software([11, 12])

    stop = False
    loop = 0

    while not stop:
        loop += 1
        read, write, error = events = select((device,), (), (device,))
        if read:
            (
                counters,
                channels,
                dma,
                fifo_half_full,
                error,
            ), tstamp = device.acknowledge_interrupt()
            if 12 in counters:
                stop = True
            if dma:
                fifo, fifo_status = device.read_fifo()
                print(str(fifo))  # , to_str(device.get_latches_values()))
                fifo.shape = -1, len(channelid2name)
                ch_data = {}
                for i, (ch_id, ch_name) in enumerate(channelid2name):
                    ch_data[ch_name] = fifo[:, i]
                new_event = {"type": "0D", "channel_data": ch_data}
                # dispatcher.send("new_data", self, new_event)
                # print("new event: {0}".format(new_event))
        if stop:
            print("Acquisition finished. Bailing out!")


if __name__ == "__main__":
    main()
