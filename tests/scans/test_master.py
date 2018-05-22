from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionMaster, AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel


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


def test_dummy_scan_without_external_channel(beacon):
    # Get controllers
    chain = AcquisitionChain()
    master = DummyMaster(None, 'master', npoints=1)
    device = DummyDevice(None, 'device', npoints=1)
    chain.add(master, device)
    # Run scan
    scan = Scan(chain, 'test', None)
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
    master.add_external_channel(device, 'pi', 'to', lambda x: 2*x)
    # Run scan
    scan = Scan(chain, 'test', None)
    scan.run()
    # Checks
    assert scan.get_data()['pi'] == [3.14]
    assert scan.get_data()['to'] == [6.28]
