import numpy
import gevent
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain, AcquisitionChannel, AcquisitionMaster
from bliss.scanning.acquisition import timer
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster, MotorMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
import pytest
import gevent
import numpy
from treelib import Node, Tree


def test_dummy_scan_without_external_channel(
    session, dummy_acq_master, dummy_acq_device
):
    # Get controllers
    chain = AcquisitionChain()
    master = dummy_acq_master.get(None, "master", npoints=1)
    device = dummy_acq_device.get(None, "device", npoints=1)
    chain.add(master, device)
    # Run scan
    scan = Scan(chain, "test", save=False)
    scan.run()
    # Checks
    assert scan.get_data()["pi"] == [3.14]


def test_dummy_scan_with_external_channel(session, dummy_acq_master, dummy_acq_device):
    # Get controllers
    chain = AcquisitionChain()
    master = dummy_acq_master.get(None, "master", npoints=1)
    device = dummy_acq_device.get(None, "device", npoints=1)
    chain.add(master, device)
    # Add external channel
    chan = device.channels[0]
    master.add_external_channel(device, chan.name, "to", lambda x: 2 * x)
    master.add_external_channel(device, chan.name, "to_int", lambda x: 2 * x, dtype=int)
    # Run scan
    scan = Scan(chain, "test", save=False)
    scan.run()
    # Checks
    assert scan.get_data()["pi"] == [3.14]
    assert scan.get_data()["to"] == [6.28]
    assert scan.get_data()["to_int"] == [6]


def test_stopiter_with_top_master(session, lima_simulator, dummy_acq_device):
    chain = AcquisitionChain()
    master = timer.SoftwareTimerMaster(0.1, npoints=2)
    lima_sim = session.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    chain.add(master, lima_master)

    device = dummy_acq_device.get(None, "device", npoints=1)
    chain.add(lima_master, device)

    scan = Scan(chain, "test")
    scan.run()
    assert device.nb_trigger == 2


def test_attach_channel(session):
    m0 = session.config.get("m0")
    m1 = session.config.get("m1")
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


def test_add_multiple_top_masters_same_name(
    session, dummy_acq_master, dummy_acq_device
):
    chain = AcquisitionChain()
    master1 = dummy_acq_master.get(None, "master")
    master2 = dummy_acq_master.get(None, "master")
    master3 = dummy_acq_master.get(None, "master")
    master4 = dummy_acq_master.get(None, "master4")
    dummy_device = dummy_acq_device.get(None, "dummy_device")

    assert chain.add(master1, master3) is None
    with pytest.raises(RuntimeError) as e_info:
        assert chain.add(master2, dummy_device)
    assert "duplicated" in str(e_info.value)
    assert chain.add(master4, dummy_device) is None


def test_multiple_top_masters(session, lima_simulator, dummy_acq_device):
    chain = AcquisitionChain()
    master1 = timer.SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    diode_sim = session.config.get("diode")
    diode_device = SamplingCounterAcquisitionDevice(diode_sim, 0.1)
    master2 = timer.SoftwareTimerMaster(0.001, npoints=50, name="timer2")
    lima_sim = session.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.001)
    # note: dummy device has 2 channels: pi and nb
    dummy_device = dummy_acq_device.get(None, "dummy_device", npoints=1)
    chain.add(lima_master, dummy_device)
    chain.add(master2, lima_master)
    chain.add(master1, diode_device)
    master1.terminator = False

    scan = Scan(chain, "test", save=False)
    scan.run()

    assert dummy_device.nb_trigger == 50
    scan_data = scan.get_data()
    assert isinstance(scan_data["elapsed_time"], numpy.ndarray)
    assert isinstance(scan_data["timer2:elapsed_time"], numpy.ndarray)
    assert isinstance(scan_data["pi"], numpy.ndarray)
    assert isinstance(scan_data["nb"], numpy.ndarray)
    assert isinstance(scan_data["diode"], numpy.ndarray)
    assert len(scan_data["elapsed_time"]) == 2
    assert len(scan_data["timer2:elapsed_time"]) == 50

    ### check structure in redis
    tree = Tree()
    for node in scan.node.iterator.walk(wait=False):
        if not node.type == "channel":
            if node.db_name == scan.node.db_name:
                tree.create_node("acquisition chain", node.db_name)
            else:
                tmp = node.db_name.split(":")
                tree.create_node(node.name, node.db_name, parent=":".join(tmp[:-1]))

    assert str(scan.acq_chain._tree) == str(tree)


def test_master_synchro(session, dummy_acq_master, dummy_acq_device):
    chain = AcquisitionChain(parallel_prepare=True)
    master = dummy_acq_master.get(None, "master", npoints=1)
    device1 = dummy_acq_device.get(None, "device1", npoints=1, sleep_time=0.1)
    device2 = dummy_acq_device.get(None, "device2", npoints=1, sleep_time=0.2)
    chain.add(master, device1)
    chain.add(master, device2)
    scan = Scan(chain, "test", save=False)
    scan.run()
    assert master.child_started == 2
    assert master.child_prepared == 2


def test_lima_reintrant_iterator(session, lima_simulator):
    simulator = session.config.get("lima_simulator")

    class TriggerMaster(AcquisitionMaster):
        def __init__(self):
            super().__init__(None, "trigger")
            self.iter_val = -1

        def __iter__(self):
            for i in range(3):
                self.iter_val = i
                yield self

        def prepare(self):
            pass

        def start(self):
            self.trigger_slaves()
            self.wait_slaves()
            self.wait_slaves_ready()
            self.trigger_slaves()
            gevent.sleep(0.1)  # avoid synchro error in Lima

        def stop(self):
            pass

    class LimaMaster(LimaAcquisitionMaster):
        @property
        def fast_synchro(self):
            return False

    trigger_mster = TriggerMaster()
    lima_mster = LimaMaster(
        simulator,
        acq_nb_frames=2,
        acq_expo_time=1e-3,
        acq_trigger_mode="INTERNAL_TRIGGER_MULTI",
        wait_frame_id=range(2),
        prepare_once=False,
        start_once=False,
    )
    chain = AcquisitionChain()
    chain.add(trigger_mster, lima_mster)
    s = Scan(chain, "test", save=False)
    # s.trace()
    with gevent.Timeout(3, "Failed"):
        s.run()
    assert trigger_mster.iter_val == 2
