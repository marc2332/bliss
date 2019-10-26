# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import numpy
import pickle as pickle
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain, AcquisitionMaster, AcquisitionDevice
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.data.node import DataNodeContainer, _get_or_create_node, sessions_list
from bliss.config.settings import scan as redis_scan
from bliss.config.settings import QueueObjSetting
from bliss.data.scan import Scan as ScanNode
from bliss.data.node import get_session_node, get_node, DataNodeIterator, DataNode
from bliss.data.channel import ChannelDataNode
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.channel import AcquisitionChannel


@pytest.fixture
def lima_session(beacon, scan_tmpdir, lima_simulator):
    session = beacon.get("lima_test_session")
    session.setup()
    session.env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)
    yield session
    session.close()


def test_parent_node(session, scan_tmpdir):
    scan_saving = session.env_dict["SCAN_SAVING"]
    scan_saving.base_path = str(scan_tmpdir)
    scan_saving.template = "{date}/test"
    redis_base_path = str(scan_tmpdir).replace("/", ":")
    parent_node = scan_saving.get_parent_node()
    assert (
        parent_node.db_name == f"test_session{redis_base_path}:{scan_saving.date}:test"
    )
    assert parent_node.type == "container"
    assert isinstance(parent_node, DataNodeContainer)


def test_scan_node(session, redis_data_conn, scan_tmpdir):
    scan_saving = session.env_dict["SCAN_SAVING"]
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 5
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, 5),
        SamplingCounterAcquisitionDevice(diode, count_time=0.01, npoints=5),
    )

    s = Scan(chain, "test_scan", scan_info={"metadata": 42})
    assert s.name == "test_scan"
    assert s.root_node.db_name == parent.db_name

    assert s.node is None

    with gevent.Timeout(5):
        s.run()

    assert isinstance(s.node, ScanNode)
    assert s.node.type == "scan"
    assert s.node.db_name == s.root_node.db_name + ":" + "1_" + s.name

    scan_node_dict = redis_data_conn.hgetall(s.node.db_name)
    assert scan_node_dict.get(b"name") == b"1_test_scan"
    assert scan_node_dict.get(b"db_name") == s.node.db_name.encode()
    assert scan_node_dict.get(b"node_type") == b"scan"
    assert scan_node_dict.get(b"parent") == s.node.parent.db_name.encode()

    scan_info_dict = redis_data_conn.hgetall(s.node.db_name + "_info")
    assert pickle.loads(scan_info_dict[b"metadata"]) == 42

    assert redis_data_conn.ttl(s.node.db_name) > 0

    roby_node_db_name = s.node.db_name + ":axis"
    scan_children_node = [roby_node_db_name]
    roby_children_node = [
        roby_node_db_name + ":roby",
        roby_node_db_name + ":simulation_diode_controller",
    ]
    assert redis_data_conn.lrange(s.node.db_name + "_children_list", 0, -1) == [
        x.encode() for x in scan_children_node
    ]
    assert redis_data_conn.lrange(roby_node_db_name + "_children_list", 0, -1) == [
        x.encode() for x in roby_children_node
    ]

    for child_node_name in scan_children_node + roby_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0

    assert sessions_list()[0].name == "test_session"


def test_interrupted_scan(session, redis_data_conn, scan_tmpdir):
    scan_saving = session.env_dict["SCAN_SAVING"]
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 10
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, 5),
        SamplingCounterAcquisitionDevice(diode, count_time=0.01, npoints=5),
    )

    s = Scan(chain, "test_scan")
    scan_task = gevent.spawn(s.run)
    gevent.sleep(0.5)
    with pytest.raises(KeyboardInterrupt):
        scan_task.kill(KeyboardInterrupt)

    assert redis_data_conn.ttl(s.node.db_name) > 0

    roby_node_db_name = s.node.db_name + ":axis"
    scan_children_node = [roby_node_db_name]
    roby_children_node = [
        roby_node_db_name + ":roby",
        roby_node_db_name + ":simulation_diode_controller:diode",
    ]

    for child_node_name in scan_children_node + roby_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0


def test_scan_data_0d(session, redis_data_conn):

    counter_name = "sim_ct_gauss"
    simul_counter = getattr(setup_globals, counter_name)
    s = scans.timescan(0.1, simul_counter, npoints=10, return_scan=True, save=False)

    assert s == scans.SCANS[-1]

    # redis key is build from node name and counter name with _data suffix
    # ":timer:<counter_name>:<counter_name>_data"
    redis_key = s.node.db_name + f":timer:{counter_name}:{counter_name}_data"
    redis_data = list(map(float, redis_data_conn.lrange(redis_key, 0, -1)))

    assert numpy.array_equal(redis_data, simul_counter.data)

    redis_keys = set(redis_scan(session.name + "*", connection=redis_data_conn))
    session_node = get_session_node(session.name)
    db_names = set([n.db_name for n in DataNodeIterator(session_node).walk(wait=False)])
    assert len(db_names) > 0
    assert db_names == redis_keys.intersection(db_names)


def test_data_iterator_event(beacon, redis_data_conn, scan_tmpdir, session):
    def iterate_channel_events(scan_db_name, channels):
        for e, n in DataNodeIterator(get_node(scan_db_name)).walk_events():
            if n.type == "channel":
                channels[n.name] = n.get(0, -1)

    scan_saving = session.env_dict["SCAN_SAVING"]
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 5
    diode = getattr(setup_globals, "diode")
    npts = 5
    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, npts),
        SamplingCounterAcquisitionDevice(diode, count_time=0.01, npoints=npts),
    )

    s = Scan(chain, "test_scan")

    # force existance of scan node before starting the scan
    s._prepare_note()

    channels_data = dict()
    iteration_greenlet = gevent.spawn(
        iterate_channel_events, s.node.db_name, channels_data
    )

    s.run()

    time.sleep(0.1)
    iteration_greenlet.kill()

    assert set(("axis:roby", diode.fullname)) == set(channels_data.keys())
    assert len(channels_data["axis:roby"]) == npts
    assert len(channels_data[diode.fullname]) == npts

    x = DataNodeIterator(get_node(s.node.db_name))
    for n in x.walk_from_last(filter="channel", wait=False):
        assert n.get(0, -1) == channels_data[n.name]
    assert isinstance(n, ChannelDataNode)


def test_lima_data_channel_node(redis_data_conn, lima_session):
    lima_sim = lima_session.env_dict["lima_simulator"]

    timescan = scans.timescan(0.1, lima_sim, npoints=1)

    image_node_db_name = "%s:timer:lima_simulator:image" % timescan.node.db_name
    image_node = _get_or_create_node(image_node_db_name)
    assert image_node.db_name == image_node_db_name
    assert image_node.fullname == "lima_simulator:image"
    assert image_node.shape == (1024, 1024)
    assert image_node.dtype == numpy.uint32


@pytest.mark.parametrize("with_roi", [False, True], ids=["without ROI", "with ROI"])
def test_reference_with_lima(redis_data_conn, lima_session, with_roi):
    lima_sim = getattr(setup_globals, "lima_simulator")

    # Roi handling
    lima_sim.roi_counters.clear()
    if with_roi:
        lima_sim.roi_counters["myroi"] = [0, 0, 1, 1]

    timescan = scans.timescan(0.1, lima_sim, npoints=3)

    session_node = get_session_node(lima_session.name)
    db_names = set([n.db_name for n in DataNodeIterator(session_node).walk(wait=False)])

    image_node_db_name = "%s:timer:lima_simulator:image" % timescan.node.db_name
    assert image_node_db_name in db_names

    live_ref_status = QueueObjSetting(
        "%s_data" % image_node_db_name, connection=redis_data_conn
    )[0]
    assert live_ref_status["last_image_saved"] == 2  # npoints-1


@pytest.mark.parametrize("with_roi", [False, True], ids=["without ROI", "with ROI"])
def test_iterator_over_reference_with_lima(redis_data_conn, lima_session, with_roi):
    npoints = 5
    exp_time = 1
    lima_sim = getattr(setup_globals, "lima_simulator")

    # Roi handling
    lima_sim.roi_counters.clear()
    if with_roi:
        lima_sim.roi_counters["myroi"] = [0, 0, 1, 1]

    session_node = _get_or_create_node(lima_session.name, node_type="session")
    iterator = DataNodeIterator(session_node)

    with gevent.Timeout(10 + 2 * (npoints + 1) * exp_time):

        def watch_scan():
            for scan_node in iterator.walk_from_last(filter="scan", include_last=False):
                scan_iterator = DataNodeIterator(scan_node)
                for event_type, node in scan_iterator.walk_events(filter="lima"):
                    if event_type == DataNodeIterator.EVENTS.NEW_DATA_IN_CHANNEL:
                        view = node.get(from_index=0, to_index=-1)
                        if len(view) == npoints:
                            return view

        watch_task = gevent.spawn(watch_scan)
        scans.timescan(exp_time, lima_sim, npoints=npoints)
        view = watch_task.get()

    view_iterator = iter(view)
    img0 = next(view_iterator)

    # make another scan -> this should make a new buffer on Lima server,
    # so images from previous view cannot be retrieved from server anymore
    scans.ct(exp_time, lima_sim)

    view_iterator2 = iter(view)

    # retrieve from file
    assert numpy.allclose(next(view_iterator2), img0)


def test_ttl_on_data_node(beacon, redis_data_conn):
    redis_data_conn.delete("testing")
    node = DataNode("test", "testing", create=True)
    node.set_ttl()
    assert redis_data_conn.ttl("testing") == DataNode.default_time_to_live
    del node
    assert redis_data_conn.ttl("testing") == DataNode.default_time_to_live

    redis_data_conn.delete("testing")
    node = DataNode("test", "testing", create=True)
    assert redis_data_conn.ttl("testing") == -1
    del node
    assert redis_data_conn.ttl("testing") == DataNode.default_time_to_live


def test_ttl_setter(session, capsys):
    heater = getattr(setup_globals, "heater")
    diode = getattr(setup_globals, "diode")
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    s = scans.loopscan(1, .1, heater, diode, run=False)
    out, err = capsys.readouterr()
    assert err == ""


def test_children_timing(beacon, session, scan_tmpdir):

    # put scan file in a tmp directory
    session.env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    diode2 = session.env_dict["diode2"]

    def walker(scan_node, event):
        # print("LISTENING TO", scan_node.db_name)
        for event_type, node in scan_node.iterator.walk_events(ready_event=event):
            # print(event_type.name, node.db_name)
            parent = node.parent
            if (
                event_type.name == "NEW_NODE"
                and parent is not None
                and parent.type == "scan"
            ):
                children = list(parent.children())
                # print(">>>", event_type.name, node.db_name, children)
                if len(children) == 0:
                    raise RuntimeError(node.db_name)
                    # pass

    s = scans.loopscan(30, .1, diode2, run=False, wait=True)

    # force existance of scan node before starting the scan
    s._prepare_note()

    event = gevent.event.Event()
    g = gevent.spawn(walker, s.node, event=event)
    event.wait()
    # print("BEFORE RUN", list([n.db_name for n in s.node.children()]))
    s.run()
    gevent.sleep(.5)
    # print("AFTER RUN", list([n.db_name for n in s.node.children()]))

    g.kill()


def test_scan_end_timing(
    session, scan_meta, dummy_acq_master, dummy_acq_device
):  # , clean_gevent):
    scan_meta.clear()

    # Get controllers
    chain = AcquisitionChain()
    master = dummy_acq_master.get(None, "master", npoints=1)
    device = dummy_acq_device.get(None, "device", npoints=1)

    def a_slow_func():
        # this sleep is the point of the test...
        # delay the filling of scan_info
        gevent.sleep(.2)
        return {"DummyDevice": "slow"}

    def fill_meta_at_scan_end(scan_meta):
        scan_meta.instrument.set("bla", a_slow_func())

    device.fill_meta_at_scan_end = fill_meta_at_scan_end
    chain.add(master, device)

    scan = Scan(chain, "test", save=False, scan_info={"instrument": {"some": "text"}})

    def g(scan_node):
        parent = scan_node.parent
        for event_type, node in parent.iterator.walk_on_new_events(filter="scan"):
            if event_type.name == "END_SCAN":
                assert node.info.get("instrument") == {
                    "DummyDevice": "slow",
                    "some": "text",
                }
                return

    # force existance of scan node before starting the scan
    scan._prepare_note()

    gg = gevent.spawn(g, scan.node)
    gevent.sleep(.1)

    scan.run()

    with gevent.Timeout(1):
        gg.get()
        # if this raises "END_SCAN" event was not emitted


def test_data_shape_of_get(default_session):
    class myAcqDev(AcquisitionDevice):
        def __init__(self):
            class dev:
                def __init__(self):
                    self.name = "test_def"

            super().__init__(dev(), npoints=7)
            self.channels.append(AcquisitionChannel("test:test", numpy.float64, (1,)))
            self.dat = self.get_data()

        def prepare(self):
            pass

        def get_data(self):
            yield numpy.arange(3)
            yield numpy.arange(5)
            yield numpy.arange(20)
            yield numpy.arange(1)
            yield numpy.arange(15)
            yield numpy.arange(15)
            yield numpy.arange(2)

        def start(self):
            dat = next(self.dat)
            # should it be possible at all to reduce the shape of a channel?
            self.channels[0].shape = dat.shape
            self.channels.update_from_iterable([dat])

        def stop(sef):
            pass

        def trigger(self):
            pass

    chain = AcquisitionChain()
    master = SoftwareTimerMaster(0.1, npoints=7, name="timer1")
    md = myAcqDev()
    chain.add(master, md)
    s = Scan(chain, name="toto")
    s.run()

    for node in s.node.iterator.walk(wait=False):
        if node.name == "test:test":
            mynode = node
            break

    assert numpy.array(mynode.get(0, 1)).dtype == numpy.float64

    assert numpy.array(mynode.get_as_array(0, 2)).dtype == numpy.float64
