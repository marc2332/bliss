from gevent.select import select
from louie import dispatcher

from ct2 import CtConfig, CtClockSrc, CtGateSrc, CtHardStartSrc, CtHardStopSrc

from bliss.common.continuous_scan import AcquisitionDevice, AcquisitionMaster
import gevent

class P201AcquisitionMaster(AcquisitionMaster):
    #master could be cN for external channels or internal for internal counter
    def __init__(self,device, nb_points=1, acq_expo_time=1., master="internal"):
        AcquisitionMaster.__init__(self, device, device.__class__.__name__, "zerod")
        self.__nb_points = nb_points
        self.__acq_expo_time = acq_expo_time
        self.__master = master

    def prepare(self) :
        device = self.device

        if self.__master.lower() == "internal":
            ct_config = CtConfig(clock_source=CtClockSrc.CLK_100_MHz,
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
                                 reset_from_hard_soft_stop=False,
                                 stop_from_hard_stop=True)
            device.set_counter_config(12, ct_config)

            device.set_counter_comparator_value(11, int(self.__acq_expo_time * 1E8))
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

    def start(self):
        if self.__master.lower() == "internal":
            self.device.set_counters_software_start((11, 12))

class P201AcquisitionDevice(AcquisitionDevice):

    def __init__(self, device, nb_points=1, acq_expo_time=1.,
                 master="internal", channels=None):
        self.__channels = channels or dict()
        AcquisitionDevice.__init__(self, device, device.__class__.__name__, "zerod",
                                   trigger_type = AcquisitionDevice.HARDWARE)

    def prepare(self):
        device = self.device
        active_channels = self.__channels.values()
        for ch_nb in active_channels:
            ct_config = self.device.get_counter_config(ch_nb)
            ct_config.gate_source = CtGateSrc.CT_12_GATE_ENVELOP
            ct_config.hard_start_source=CtHardStartSrc.CT_12_START
            ct_config.hard_stop_source=CtHardStopSrc.CT_11_EQ_CMP_11
            ct_config.hard_start_source=CtHardStartSrc.SOFTWARE
            ct_config.hard_stop_source=CtHardStopSrc.SOFTWARE
            ct_config.reset_from_hard_soft_stop=True
            ct_config.stop_from_hard_stop=False
            device.set_counter_config(ch_nb, ct_config)

        # counter 11 will latch all active counters/channels
        latch_sources = dict([(ct, 11) for ct in active_channels + [12]])
        device.set_counters_latch_sources(latch_sources)

        # counter 12 counter-to-latch signal will trigger DMA; at each DMA
        # trigger, all active counters (+ counter 12) are stored to FIFO
        # (counter 11 cannot be the one to trigger because it is not
        # being latched)
        device.set_DMA_enable_trigger_latch((12,), active_channels + [12])
        device.set_counters_software_enable(active_channels)

        # make sure there is a FIFO before starting
        self.__fifo = device.fifo

    def start(self):
        self.device.set_counters_software_start(self.__channels.values())

    def reading(self):
        device = self.device
        chid2name = sorted(((nb,name) for name,nb in self.__channels.iteritems()))
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
