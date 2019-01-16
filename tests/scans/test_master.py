import numpy
import gevent
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionMaster, AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.scanning.acquisition import timer
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster, MotorMaster


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
        self.channels.append(AcquisitionChannel("pi", float, ()))

    def prepare(self):
        pass

    def start(self):
        self.channels.update({"pi": 3.14})

    def trigger(self):
        pass

    def stop(self):
        pass


class DummySlave(AcquisitionDevice):
    def __init__(self, *args, **kwargs):
        super(DummySlave, self).__init__(*args, **kwargs)
        self.channels.append(AcquisitionChannel("nb", float, ()))
        self.nb_trigger = 0

    def prepare(self):
        pass

    def start(self):
        pass

    def trigger(self):
        self.channels.update({"nb": self.nb_trigger})
        self.nb_trigger += 1

    def stop(self):
        pass


def test_dummy_scan_without_external_channel(beacon):
    # Get controllers
    chain = AcquisitionChain()
    master = DummyMaster(None, "master", npoints=1)
    device = DummyDevice(None, "device", npoints=1)
    chain.add(master, device)
    # Run scan
    scan = Scan(chain, "test", save=False)
    scan.run()
    # Checks
    assert scan.get_data()["pi"] == [3.14]


def test_dummy_scan_with_external_channel(beacon):
    # Get controllers
    chain = AcquisitionChain()
    master = DummyMaster(None, "master", npoints=1)
    device = DummyDevice(None, "device", npoints=1)
    chain.add(master, device)
    # Add external channel
    master.add_external_channel(device, "pi", "to", lambda x: 2 * x)
    master.add_external_channel(device, "pi", "to_int", lambda x: 2 * x, dtype=int)
    # Run scan
    scan = Scan(chain, "test", save=False)
    scan.run()
    # Checks
    assert scan.get_data()["pi"] == [3.14]
    assert scan.get_data()["to"] == [6.28]
    assert scan.get_data()["to_int"] == [6]


def test_stopiter_with_top_master(beacon, lima_simulator):
    chain = AcquisitionChain()
    master = timer.SoftwareTimerMaster(0.1, npoints=2)
    lima_sim = beacon.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    chain.add(master, lima_master)

    device = DummySlave(None, "device", npoints=1)
    chain.add(lima_master, device)

    scan = Scan(chain, "test")
    scan.run()
    assert device.nb_trigger == 2


def test_attach_channel(beacon):
    m0 = beacon.get("m0")
    m1 = beacon.get("m1")
    chain = AcquisitionChain()
    top_master = LinearStepTriggerMaster(2, m0, 0, 0.1)
    second_master = MotorMaster(m1, 0, 1e-6, 0.01)
    # hack add manually a channel
    ext_channel = AcquisitionChannel(m1.name, numpy.double, ())
    second_master.channels.append(ext_channel)
    real_trigger = second_master.trigger

    def new_trigger(*args):
        real_trigger(*args)
        gevent.sleep(0)
        ext_channel.emit([1, 2, 3])

    second_master.trigger = new_trigger

    chain.add(top_master, second_master)
    second_master.attach_channels(top_master, m1.name)

    scan = Scan(chain, "test", save=False)
    scan.run()
    data = scan.get_data()
    assert len(data["m1"]) == 6
    assert len(data["m0"]) == len(data["m1"])
