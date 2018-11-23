import gevent
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionMaster, AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice


class DummyMaster(AcquisitionMaster):
    def __init__(self, *args, **kwargs):
        AcquisitionMaster.__init__(self, *args, **kwargs)
        self.child_prepared = 0
        self.child_started = 0

    def prepare(self):
        self.wait_slaves_prepare()
        self.child_prepared = sum((slave.prepared_flag for slave in self.slaves))

    def start(self):
        self.child_started = sum((slave.started_flag for slave in self.slaves))

    def trigger(self):
        pass

    def stop(self):
        pass


class DummyDevice(AcquisitionDevice):
    def __init__(self, *args, **kwargs):
        self.sleep_time = kwargs.pop("sleep_time")
        AcquisitionDevice.__init__(self, *args, **kwargs)
        self.prepared_flag = False
        self.started_flag = False

    def prepare(self):
        gevent.sleep(self.sleep_time)
        self.prepared_flag = True

    def start(self):
        gevent.sleep(self.sleep_time)
        self.started_flag = True

    def trigger(self):
        pass

    def stop(self):
        pass


def test_master_synchro(beacon):
    chain = AcquisitionChain(parallel_prepare=True)
    master = DummyMaster(None, "master", npoints=1)
    device1 = DummyDevice(None, "device1", npoints=1, sleep_time=0.1)
    device2 = DummyDevice(None, "device2", npoints=1, sleep_time=0.2)
    chain.add(master, device1)
    chain.add(master, device2)
    scan = Scan(chain, "test", save=False)
    scan.run()
    assert master.child_started == 2
    assert master.child_prepared == 2
