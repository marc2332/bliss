# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import numpy
import pickle as pickle
from bliss import setup_globals, current_session
from bliss.common import scans
from bliss.scanning.scan import Scan, ScanState
from bliss.scanning.chain import AcquisitionChain, AcquisitionMaster, AcquisitionSlave
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.config.settings import scan as redis_scan
from bliss.config.streaming import DataStream, StreamStopReadingHandler
from bliss.data.nodes.scan import Scan as ScanNode
from bliss.data.node import (
    get_session_node,
    get_node,
    DataNodeIterator,
    DataNode,
    DataNodeContainer,
    _get_or_create_node,
    _get_node_object,
    sessions_list,
)
from bliss.data.nodes.channel import ChannelDataNode
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.channel import AcquisitionChannel


@pytest.fixture
def lima_session(beacon, scan_tmpdir, lima_simulator):
    session = beacon.get("lima_test_session")
    session.setup()
    session.scan_saving.base_path = str(scan_tmpdir)
    yield session
    session.close()


def test_parent_node(session, scan_tmpdir):
    scan_saving = session.scan_saving
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
    scan_saving = session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 5
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, 5),
        SamplingCounterAcquisitionSlave(diode, count_time=0.01, npoints=5),
    )

    s = Scan(chain, "test_scan", scan_info={"metadata": 42})
    assert s.name == "test_scan"
    assert s.node is None

    with gevent.Timeout(5):
        s.run()

    assert s.root_node.db_name == parent.db_name
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
        roby_node_db_name + ":simulation_diode_sampling_controller",
    ]

    def children(node_name):
        raw_children = redis_data_conn.xrange(node_name + "_children_list", "-", "+")
        return [v.get(b"child") for i, v in raw_children]

    assert children(s.node.db_name) == [x.encode() for x in scan_children_node]
    assert children(roby_node_db_name) == [x.encode() for x in roby_children_node]

    for child_node_name in scan_children_node + roby_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0

    assert sessions_list()[0].name == "test_session"


def test_interrupted_scan(session, redis_data_conn, scan_tmpdir):
    """
    Start a scan and simulate a ctrl-c.
    """
    scan_saving = session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)

    m = getattr(setup_globals, "roby")
    m.velocity = 10
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, 5),
        SamplingCounterAcquisitionSlave(diode, count_time=0.01, npoints=5),
    )

    s = Scan(chain, "test_scan")

    assert s._Scan__state == ScanState.IDLE

    # Run scan in greenlet
    scan_task = gevent.spawn(s.run)

    # IDLE->PREPARING->STARTING->STOPPING->DONE
    # Wait for scan state to be STARTING
    with gevent.Timeout(2):
        s.wait_state(ScanState.STARTING)

    assert s._Scan__state == ScanState.STARTING

    # Stop the scan like a ctrl-c
    with pytest.raises(KeyboardInterrupt):
        scan_task.kill(KeyboardInterrupt)

    assert redis_data_conn.ttl(s.node.db_name) > 0

    roby_node_db_name = s.node.db_name + ":axis"
    scan_children_node = [roby_node_db_name]
    roby_children_node = [
        roby_node_db_name + ":roby",
        roby_node_db_name + ":simulation_diode_sampling_controller:diode",
    ]

    for child_node_name in scan_children_node + roby_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0


def test_scan_data_0d(session, redis_data_conn):
    simul_counter = session.env_dict.get("sim_ct_gauss")
    s = scans.timescan(0.1, simul_counter, npoints=10, return_scan=True, save=False)

    assert s == current_session.scans[-1]

    # redis key is build from node name and counter name with _data suffix
    # ":timer:<counter_name>:<counter_name>_data"
    redis_key = s.node.db_name + f":timer:{simul_counter.fullname}_data"
    raw_stream_data = redis_data_conn.xrange(redis_key, "-", "+")
    raw_data = (numpy.loads(v.get(b"data")) for i, v in raw_stream_data)
    redis_data = list(raw_data)
    assert numpy.array_equal(redis_data, simul_counter.data)

    redis_keys = set(redis_scan(session.name + "*", connection=redis_data_conn))
    session_node = get_session_node(session.name)
    db_names = set([n.db_name for n in DataNodeIterator(session_node).walk(wait=False)])
    assert len(db_names) > 0
    assert db_names == redis_keys.intersection(db_names)


def test_data_iterator_event(beacon, redis_data_conn, scan_tmpdir, session):
    def iterate_channel_events(scan_db_name, channels):
        for e, n, data in DataNodeIterator(get_node(scan_db_name)).walk_events():
            if e == e.NEW_DATA:
                if n.type == "channel":
                    channels[n.name] = n.get(0, -1)

    scan_saving = session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 5
    diode = getattr(setup_globals, "diode")
    npts = 5
    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, npts),
        SamplingCounterAcquisitionSlave(diode, count_time=0.01, npoints=npts),
    )

    s = Scan(chain, "test_scan")

    # force existance of scan node before starting the scan
    s._prepare_node()

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
        assert all(n.get(0, -1) == channels_data[n.name])
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

    stream_status = DataStream(
        "%s_data" % image_node_db_name, connection=redis_data_conn
    )
    index, ref_status = stream_status.rev_range(count=1)[0]

    live_ref_status = pickle.loads(ref_status.get(b"__data__"))
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
                for event_type, node, data in scan_iterator.walk_events(filter="lima"):
                    if event_type == event_type.NEW_DATA:
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
    session.scan_saving.base_path = str(scan_tmpdir)

    diode2 = session.env_dict["diode2"]

    def walker(scan_node):
        # print("LISTENING TO", scan_node.db_name)
        for event_type, node, event_data in scan_node.iterator.walk_events():
            if event_type != event_type.NEW_NODE:
                continue
            # print(event_type.name, node.db_name)
            parent = node.parent
            if parent is not None and parent.type == "scan":
                children = list(parent.children())
                # print(">>>", event_type.name, node.db_name, children)
                if len(children) == 0:
                    raise RuntimeError(node.db_name)
                    # pass

    s = scans.loopscan(30, .1, diode2, run=False)

    # force existance of scan node before starting the scan
    s._prepare_node()

    g = gevent.spawn(walker, s.node)
    # print("BEFORE RUN", list([n.db_name for n in s.node.children()]))
    s.run()
    # print("AFTER RUN", list([n.db_name for n in s.node.children()]))

    g.kill()


def test_scan_end_timing(
    session, scan_meta, dummy_acq_master, dummy_acq_device
):  # , clean_gevent):
    scan_meta.clear()

    # Get controllers
    chain = AcquisitionChain()
    master = dummy_acq_master.get(None, name="master", npoints=1)
    device = dummy_acq_device.get(None, name="device", npoints=1)

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

    event = gevent.event.Event()

    def g(scan_node):
        parent = scan_node.parent
        event.set()
        first_index = int(time.time() * 1000)
        first_index -= 100  # subsctract 100ms
        # Can't use **walk_on_new_events** because
        # in this test we force to create nodes before starting scan
        # we will use **walk_event** with current time passed 100ms
        # which is equivalent to **walk_on_new_events** if we have started it
        # 100ms before.
        for event_type, node, event_data in parent.iterator.walk_events(
            first_index=first_index, filter="scan"
        ):
            if event_type == event_type.END_SCAN:
                assert node.info.get("instrument") == {
                    "DummyDevice": "slow",
                    "some": "text",
                }
                return

    # force existance of scan node before starting the scan
    scan._prepare_node()

    gg = gevent.spawn(g, scan.node)
    with gevent.Timeout(1.):
        event.wait()
    scan.run()

    with gevent.Timeout(1.):
        gg.get()
        # if this raises "END_SCAN" event was not emitted


def test_data_shape_of_get(default_session):
    class myAcqDev(AcquisitionSlave):
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


def test_stop_before_any_walk_event(default_session):
    session_node = get_session_node(default_session.name)
    event = gevent.event.Event()

    def spawn_walk(stop_handler):
        event.set()
        for node in session_node.iterator.walk(
            stream_stop_reading_handler=stop_handler
        ):
            pass

    stop_handler = StreamStopReadingHandler()
    task = gevent.spawn(spawn_walk, stop_handler)
    with gevent.Timeout(1.):
        event.wait()

    stop_handler.stop()
    with gevent.Timeout(1.):
        task.get()


def test_stop_after_first_walk_event(session):
    session_node = get_session_node(session.name)
    event = gevent.event.Event()

    def spawn_walk(stop_handler):
        for node in session_node.iterator.walk(
            stream_stop_reading_handler=stop_handler
        ):
            event.set()

    stop_handler = StreamStopReadingHandler()
    task = gevent.spawn(spawn_walk, stop_handler)

    diode = session.env_dict["diode"]
    scans.loopscan(1, 0, diode)

    with gevent.Timeout(1.):
        event.wait()

    stop_handler.stop()
    with gevent.Timeout(1.):
        task.get()


def _count_node_events(beforestart, session, db_name, node_type=None):
    diode = session.env_dict["diode"]
    s = scans.ct(0.1, diode, run=not beforestart)
    startlistening_event = gevent.event.Event()
    startlistening_event.clear()
    events = {}

    def walk_scan_events():
        it = _get_node_object(node_type, db_name, None, None).iterator
        startlistening_event.set()
        for e, n, d in it.walk_events():
            events.setdefault(e.name, []).append(n.db_name)

    g = gevent.spawn(walk_scan_events)
    try:
        with gevent.Timeout(5):
            startlistening_event.wait()
        if beforestart:
            scan_greenlet = gevent.spawn(s.run)
            scan_greenlet.get()
    finally:
        gevent.sleep(0.1)
        g.kill()

    return events


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_session_node(beforestart, session):
    if not beforestart:
        pytest.xfail("Channels streams are added too late")
    events = _count_node_events(beforestart, session, session.name)
    # New node events: root nodes, scan, scan master (timer),
    #                  epoch, elapsed_time, diode controller, diode
    assert set(events.keys()) == {"NEW_NODE", "NEW_DATA", "END_SCAN"}
    # One less because the NEW_NODE event for session.name is
    # not emitted on node session.name
    nroot = len(session.scan_saving._db_path_keys) - 1
    assert len(events["NEW_NODE"]) == nroot + 6
    assert len(events["NEW_DATA"]) == 3
    assert len(events["END_SCAN"]) == 1


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_wrong_session_node(beforestart, session):
    events = _count_node_events(beforestart, session, session.name[:-1])
    assert not events


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_scan_node(beforestart, session):
    if not beforestart:
        pytest.xfail("Channels streams are added too late")
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct"
    events = _count_node_events(beforestart, session, db_name, node_type="scan")
    # New node events: scan master (timer), epoch, elapsed_time,
    #                  diode controller, diode
    assert set(events.keys()) == {"NEW_NODE", "NEW_DATA", "END_SCAN"}
    assert len(events["NEW_NODE"]) == 5
    assert len(events["NEW_DATA"]) == 3
    assert len(events["END_SCAN"]) == 1


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_master_node(beforestart, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct:timer"
    events = _count_node_events(beforestart, session, db_name)
    # New node events: epoch, elapsed_time, diode controller, diode
    assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
    assert len(events["NEW_NODE"]) == 4
    assert len(events["NEW_DATA"]) == 3


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_controller_node(beforestart, session):
    db_name = (
        session.scan_saving.scan_parent_db_name
        + ":_1_ct:timer:simulation_diode_sampling_controller"
    )
    events = _count_node_events(beforestart, session, db_name)
    # New node events: diode
    assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
    assert len(events["NEW_NODE"]) == 1
    assert len(events["NEW_DATA"]) == 1


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_masterchannel_node(beforestart, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct:timer:elapsed_time"
    events = _count_node_events(beforestart, session, db_name, node_type="channel")
    assert set(events.keys()) == {"NEW_DATA"}
    assert len(events["NEW_DATA"]) == 1


@pytest.mark.parametrize("beforestart", [True, False])
def test_events_on_controllerchannel_node(beforestart, session):
    db_name = (
        session.scan_saving.scan_parent_db_name
        + ":_1_ct:timer:simulation_diode_sampling_controller:diode"
    )
    events = _count_node_events(beforestart, session, db_name, node_type="channel")
    assert set(events.keys()) == {"NEW_DATA"}
    assert len(events["NEW_DATA"]) == 1


def test_scan_numbering(default_session, beacon, scan_tmpdir):
    scan_saving = default_session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    diode = beacon.get("diode")

    l = scans.loopscan(1, .1, diode, save=True)
    assert "number" in repr(l)
    nodename = l.node.db_name.split(":")[-1]
    assert nodename[0] != "_"

    l = scans.loopscan(1, .1, diode, save=False)
    assert "number" not in repr(l)
    nodename = l.node.db_name.split(":")[-1]
    assert nodename[0] == "_"


def test_no_ct_in_scans_queue(beacon, default_session):
    diode = beacon.get("diode")
    scans.loopscan(1, .1, diode, save=False)
    assert len(default_session.scans) == 1
    scans.ct(.1, diode)
    assert len(default_session.scans) == 1
    scans.sct(.1, diode, save=False)
    assert len(default_session.scans) == 1
