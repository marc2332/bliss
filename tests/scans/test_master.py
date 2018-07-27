from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionMaster, AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.scanning.acquisition import timer
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster

class DummyMaster(AcquisitionMaster):

    def prepare(self):
        pass

    def start(self):
        pass

    def trigger(self):
        pass

    def stop(self):
        pass


class DummyDevice(AcquisitionDevice):

    def __init__(self, *args, **kwargs):
        super(DummyDevice, self).__init__(*args, **kwargs)
        self.channels.append(AcquisitionChannel('pi', float, ()))

    def prepare(self):
        pass

    def start(self):
        self.channels.update({'pi': 3.14})

    def trigger(self):
        pass

    def stop(self):
        pass

class DummySlave(AcquisitionDevice):

    def __init__(self, *args, **kwargs):
        super(DummySlave, self).__init__(*args, **kwargs)
        self.channels.append(AcquisitionChannel('nb', float, ()))
        self.nb_trigger = 0
        
    def prepare(self):
        pass

    def start(self):
        pass

    def trigger(self):
        self.channels.update({'nb': self.nb_trigger})
        self.nb_trigger += 1

    def stop(self):
        pass


def test_dummy_scan_without_external_channel(beacon):
    # Get controllers
    chain = AcquisitionChain()
    master = DummyMaster(None, 'master', npoints=1)
    device = DummyDevice(None, 'device', npoints=1)
    chain.add(master, device)
    # Run scan
    scan = Scan(chain, 'test', writer=None)
    scan.run()
    # Checks
    assert scan.get_data()['pi'] == [3.14]


def test_dummy_scan_with_external_channel(beacon):
    # Get controllers
    chain = AcquisitionChain()
    master = DummyMaster(None, 'master', npoints=1)
    device = DummyDevice(None, 'device', npoints=1)
    chain.add(master, device)
    # Add external channel
    cleanup1 = master.add_external_channel(
        device, 'pi', 'to', lambda x: 2*x)
    cleanup2 = master.add_external_channel(
        device, 'pi', 'to_int', lambda x: 2*x,dtype=int)
    # Run scan
    scan = Scan(chain, 'test', writer=None)
    scan.run()
    # Checks
    assert scan.get_data()['pi'] == [3.14]
    assert scan.get_data()['to'] == [6.28]
    assert scan.get_data()['to_int'] == [6]
    # Cleanup
    cleanup1()
    cleanup2()

def test_stopiter_with_top_master(beacon, lima_simulator):
    chain = AcquisitionChain()
    master = timer.SoftwareTimerMaster(0.1,npoints=2)
    lima_sim = beacon.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim,acq_nb_frames=1,
                                        acq_expo_time=0.1)
    chain.add(master,lima_master)

    device = DummySlave(None, 'device', npoints=1)
    chain.add(lima_master,device)
   
    scan = Scan(chain, 'test')
    scan.run()
    assert device.nb_trigger == 2

