# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from gevent.select import select
from bliss.common.event import dispatcher
from bliss.controllers.ct2 import CtConfig, CtClockSrc, CtGateSrc, CtHardStartSrc, CtHardStopSrc
import numpy
from bliss.common.continuous_scan import AcquisitionDevice, AcquisitionMaster, AcquisitionChannel
import gevent

class P201AcquisitionMaster(AcquisitionMaster):
    #master could be cN for external channels or internal for internal counter
    def __init__(self,device, nb_points=1, acq_expo_time=1., master="internal"):
        AcquisitionMaster.__init__(self, device, device.__class__.__name__, "zerod", nb_points)
        self.__nb_points = nb_points
        self.__acq_expo_time = acq_expo_time
        self.__master = master.lower()

    def prepare(self) :
        device = self.device

        if self.__master == "internal":
            ct_config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                                 gate_source=CtGateSrc.CT_12_GATE_ENVELOP,
                                 hard_start_source=CtHardStartSrc.CT_12_START,
                                 hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=False)
            device.set_counter_config(11, ct_config)
            ct_config = CtConfig(clock_source=CtClockSrc.INC_CT_11_STOP,
                                 gate_source=CtGateSrc.GATE_CMPT,
                                 hard_start_source=CtHardStartSrc.SOFTWARE,
                                 hard_stop_source=CtHardStopSrc.CT_12_EQ_CMP_12,
                                 reset_from_hard_soft_stop=True,
                                 stop_from_hard_stop=True)
            device.set_counter_config(12, ct_config)

            device.set_counter_comparator_value(11, int(self.__acq_expo_time * 1E6))
            device.set_counter_comparator_value(12, self.__nb_points)

            # dma transfer and error will trigger DMA; also counter 12 stop
            # should trigger an interrupt (this way we know that the
            # acquisition has finished without having to query the
            # counter 12 status)
            device.set_interrupts(counters=(12,), dma=True, error=True)

            # make master enabled by software
            device.set_counters_software_enable([11, 12])
        else:
            raise NotImplementedError()

    def trigger(self) :
        #@todo to be integrate into framework
        tasks = []
        for slave in self.slaves:
            tasks.append(gevent.spawn(slave._start))
        gevent.joinall(tasks)
        self.start()

    def start(self):
        if self.__master == "internal":
            self.device.set_counters_software_start((11, 12))

    def stop(self):
        #TODO: call proper stop method
        pass

class P201AcquisitionDevice(AcquisitionDevice):

    def __init__(self, device, nb_points=1, acq_expo_time=1.,
                 master="internal", channels=None):
        self.__channels = channels or dict()
        self.__all_channels = dict(channels)
        self.__all_channels.update({"timer": 11, "point_nb": 12})
        self.__master = master.lower()
        AcquisitionDevice.__init__(self, device, device.__class__.__name__, "zerod", nb_points,
                                   trigger_type = AcquisitionDevice.HARDWARE)
        self.channels.extend((AcquisitionChannel(name, numpy.uint32, (1,)) for name in self.__all_channels))

    def prepare(self):
        device = self.device
        channels = self.__channels.values()
        all_channels = self.__all_channels.values()
        for ch_nb in channels:
            ct_config = self.device.get_counter_config(ch_nb)
            ct_config.gate_source = CtGateSrc.CT_12_GATE_ENVELOP
            ct_config.hard_start_source=CtHardStartSrc.CT_12_START
            ct_config.hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11
            ct_config.reset_from_hard_soft_stop=True
            ct_config.stop_from_hard_stop=False
            device.set_counter_config(ch_nb, ct_config)

        # counter 11 will latch all active counters/channels
        latch_sources = dict([(ct, 11) for ct in all_channels])
        device.set_counters_latch_sources(latch_sources)

        # counter 11 counter-to-latch signal will trigger DMA; at each DMA
        # trigger, all active counters (including counters 11 (timer)
        # and 12 (point_nb)) are stored to FIFO
        device.set_DMA_enable_trigger_latch((11,), all_channels)
        device.set_counters_software_enable(channels)

    def start(self):
        self.device.set_counters_software_start(self.__channels.values())

    def stop(self):
        #TODO: call proper stop method
        pass

    def reading(self):
        device = self.device
        chid2name = sorted(((nb, name) for name, nb in self.__all_channels.iteritems()))
        stop = False
        while not stop:
            read, write, error = select((self.device,),(), (self.device))
            if error:
                raise Exception("p201 select error on %s" % error)
            if read:
                (counters, channels, dma, fifo_half_full, err), tstamp = \
                    device.acknowledge_interrupt()
                if err:
                    raise Exception("p201 error")
                if 12 in counters:
                    stop = True
                if dma:
                    data, fifo_status = self.device.read_fifo()
                    #data.shape = -1, len(chanelid2name)
                    ch_data = {}
                    for i, (ch_id, ch_name) in enumerate(chid2name):
                        ch_data[ch_name] = data[:,i]
                    new_event = {"type": "zerod", "channel_data": ch_data}
                    dispatcher.send("new_data", self, new_event)
