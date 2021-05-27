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
import itertools
import pickle
import logging
from collections import OrderedDict

from bliss import setup_globals, current_session
from bliss.common import scans
from bliss.scanning.scan import Scan, ScanState, ScanAbort
from bliss.scanning.chain import AcquisitionChain, AcquisitionMaster, AcquisitionSlave
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.config.settings import scan as redis_scan
from bliss.config.streaming import DataStream, DataStreamReaderStopHandler
from bliss.data.nodes.scan import ScanNode
from bliss.data.node import (
    get_session_node,
    get_node,
    DataNode,
    DataNodeContainer,
    get_or_create_node,
    datanode_factory,
    sessions_list,
    get_last_saved_scan,
    get_filtered_nodes,
)
from bliss.data.nodes.channel import ChannelDataNode
from bliss.data.events.channel import ChannelDataEvent
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.channel import AcquisitionChannel


@pytest.fixture
def lima_session(beacon, scan_tmpdir, lima_simulator):
    session = beacon.get("lima_test_session")
    session.setup()
    session.scan_saving.base_path = str(scan_tmpdir)
    yield session
    session.close()


def test_parent_node(session):
    scan_saving = session.scan_saving
    scan_saving.template = "{date}/test"
    redis_base_path = scan_saving.base_path.replace("/", ":")
    parent_node = scan_saving.get_parent_node()
    assert (
        parent_node.db_name.rpartition(":")[0]
        == f"test_session{redis_base_path}:{scan_saving.date}"
    )
    assert parent_node.parent.type == "container"
    assert isinstance(parent_node, DataNodeContainer)
    assert (
        parent_node.db_name == f"test_session{redis_base_path}:{scan_saving.date}:test"
    )
    assert parent_node.type == "container"
    assert isinstance(parent_node, DataNodeContainer)


def test_scan_node(session, redis_data_conn, enable_ttl):
    scan_saving = session.scan_saving
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

    for db_name in redis_data_conn.keys("*"):
        assert redis_data_conn.ttl(db_name) > 0

    roby_node_db_name = s.node.db_name + ":axis"
    scan_children_node = [roby_node_db_name]
    roby_children_node = [
        roby_node_db_name + ":roby",
        roby_node_db_name + ":simulation_diode_sampling_controller",
    ]

    def children(node_name):
        raw_children = redis_data_conn.xrange(node_name + "_children_list", "-", "+")
        return [v.get(b"db_name") for i, v in raw_children]

    assert children(s.node.db_name) == [x.encode() for x in scan_children_node]
    assert children(roby_node_db_name) == [x.encode() for x in roby_children_node]

    for child_node_name in scan_children_node + roby_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0

    assert sessions_list()[0].name == "test_session"


def test_interrupted_scan(session, redis_data_conn, enable_ttl):
    """
    Start a scan and simulate a ctrl-c.
    """
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
    with pytest.raises(ScanAbort):
        scan_task.kill(KeyboardInterrupt)
        scan_task.get()

    assert redis_data_conn.ttl(s.node.db_name) > 0

    roby_node_db_name = s.node.db_name + ":axis"
    scan_children_node = [roby_node_db_name]
    roby_children_node = [
        roby_node_db_name + ":roby",
        roby_node_db_name + ":simulation_diode_sampling_controller:diode",
    ]

    for child_node_name in scan_children_node + roby_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0


def _validate_node_indexing(node, shape, dtype, npoints, expected_data, extract):
    assert node.shape == shape
    assert node.dtype == dtype
    assert len(node) == npoints
    assert numpy.array_equal(expected_data, extract(node.get(0, -1)))
    assert numpy.array_equal(expected_data, extract(node.get_as_array(0, -1)))
    assert numpy.array_equal(expected_data[0], extract(node.get(0), slice=False))
    assert numpy.array_equal(
        expected_data[0], extract(node.get_as_array(0), slice=False)
    )

    # Integer indexing
    assert extract(node[2]).dtype == node.dtype
    assert numpy.equal(expected_data[2], extract(node[2], slice=False))
    assert numpy.equal(expected_data[-2], extract(node[-2], slice=False))
    with pytest.raises(IndexError):
        extract(node[npoints], slice=False)

    # Slice indexing
    assert isinstance(extract(node[1:3]), numpy.ndarray)
    assert numpy.array_equal(expected_data, extract(node[:]))
    assert numpy.array_equal(expected_data, extract(node[0:npoints]))
    assert numpy.array_equal(expected_data, extract(node[0 : npoints + 1]))
    assert numpy.array_equal(expected_data[1:], extract(node[1:]))
    assert numpy.array_equal(expected_data[:-1], extract(node[:-1]))
    assert numpy.array_equal(expected_data[-1:], extract(node[-1:]))
    assert numpy.array_equal(expected_data[1:2], extract(node[1:2]))
    assert numpy.array_equal(expected_data[1:3], extract(node[1:3]))
    assert numpy.array_equal(expected_data[-3:-1], extract(node[-3:-1]))
    assert numpy.array_equal(extract(node[1:1]), [])
    assert numpy.array_equal(extract(node[npoints:]), [])
    assert numpy.array_equal(extract(node[npoints + 1 : npoints + 2]), [])
    with pytest.raises(IndexError):
        extract(node[3:1])


def test_scan_data_0d(session, redis_data_conn):
    simul_counter = session.env_dict.get("sim_ct_gauss")
    npoints = 10
    s = scans.timescan(
        0.1, simul_counter, npoints=npoints, return_scan=True, save=False
    )
    assert s == current_session.scans[-1]

    # Check the raw event stream
    db_name = f"{s.node.db_name}:timer:{simul_counter.fullname}"
    redis_key = db_name + "_data"
    events = redis_data_conn.xrange(redis_key, "-", "+")
    expected_data = list(numpy.loads(raw.get(b"__DATA__")) for i, raw in events)
    assert numpy.array_equal(expected_data, simul_counter.data)

    # Check the generated Redis keys
    redis_keys = set(redis_scan(session.name + "*", connection=redis_data_conn))
    session_node = get_session_node(session.name)
    db_names = set([n.db_name for n in session_node.walk(wait=False)])
    assert len(db_names) > 0
    assert db_names == redis_keys.intersection(db_names)

    # Check DataNode indexing
    node = get_node(db_name)
    assert node.db_name == db_name
    assert node.fullname == "simulation_counter_controller:sim_ct_gauss"

    def extract(arr, slice=True):
        return arr

    _validate_node_indexing(node, tuple(), float, npoints, expected_data, extract)


def test_lima_data_channel_node(lima_session, redis_data_conn):
    lima_sim = lima_session.env_dict["lima_simulator"]
    npoints = 10
    s = scans.timescan(0.1, lima_sim, npoints=npoints)

    # Check the raw event stream
    db_name = f"{s.node.db_name}:timer:{lima_sim.fullname}:image"
    redis_key = db_name + "_data"
    events = redis_data_conn.xrange(redis_key, "-", "+")
    expected_data = list(pickle.loads(raw.get(b"__STATUS__")) for i, raw in events)
    assert expected_data[-1]["last_image_acquired"] == npoints - 1

    # Check the generated Redis keys
    redis_keys = set(redis_scan(lima_session.name + "*", connection=redis_data_conn))
    session_node = get_session_node(lima_session.name)
    db_names = set([n.db_name for n in session_node.walk(wait=False)])
    assert len(db_names) > 0
    assert db_names == redis_keys.intersection(db_names)

    # Check DataNode indexing
    node = get_node(db_name)
    assert node.db_name == db_name
    assert node.fullname == "lima_simulator:image"
    expected_data = numpy.arange(1, npoints + 1) * 100

    def extract(view, slice=True):
        if slice:
            arr = view[:]
        else:
            try:
                arr = view.as_array()
            except AttributeError:
                arr = view
        if arr.size:
            return arr.max(axis=(-1, -2))
        else:
            return arr

    _validate_node_indexing(
        node, (1024, 1024), numpy.uint32, npoints, expected_data, extract
    )


def test_data_iterator_event(beacon, redis_data_conn, session):
    def iterate_channel_events(scan_db_name, channels):
        for e, n, data in get_node(scan_db_name).walk_events():
            if e == e.NEW_DATA:
                if n.type == "channel":
                    channels[n.name] = n.get(0, -1)

    scan_saving = session.scan_saving
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

    x = get_node(s.node.db_name)
    for n in x.walk_from_last(include_filter="channel", wait=False):
        assert all(n.get(0, -1) == channels_data[n.name])
    assert isinstance(n, ChannelDataNode)


@pytest.mark.parametrize("with_roi", [False, True], ids=["without ROI", "with ROI"])
def test_reference_with_lima(redis_data_conn, lima_session, with_roi):
    lima_sim = getattr(setup_globals, "lima_simulator")

    # Roi handling
    lima_sim.roi_counters.clear()
    if with_roi:
        lima_sim.roi_counters["myroi"] = [0, 0, 1, 1]

    timescan = scans.timescan(0.1, lima_sim, npoints=3)

    session_node = get_session_node(lima_session.name)
    db_names = set([n.db_name for n in session_node.walk(wait=False)])

    image_node_db_name = "%s:timer:lima_simulator:image" % timescan.node.db_name
    assert image_node_db_name in db_names

    stream_status = DataStream(
        "%s_data" % image_node_db_name, connection=redis_data_conn
    )
    index, ref_status = stream_status.rev_range(count=1)[0]

    live_ref_status = pickle.loads(ref_status.get(b"__STATUS__"))
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

    session_node = get_or_create_node(lima_session.name, node_type="session")

    with gevent.Timeout(10 + 2 * (npoints + 1) * exp_time):

        def watch_scan():
            for scan_node in session_node.walk_from_last(
                include_filter="scan", include_last=False
            ):
                for event_type, node, data in scan_node.walk_events(
                    include_filter="lima"
                ):
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


def test_corrupt_lima_data_channel_node(lima_session, redis_data_conn):
    lima_sim = lima_session.env_dict["lima_simulator"]
    npoints = 10
    s = scans.timescan(0.1, lima_sim, npoints=npoints)

    images = []
    for ev in s.node.walk_events(wait=False, include_filter="lima"):
        if ev.type == ev.type.NEW_DATA:
            images.extend(ev.data.data)
    assert len(images) == npoints

    # Remove the static lima info (contains lima_version, directory, ...)
    queue_ref_key = f"{s.node.db_name}:timer:{lima_sim.fullname}:image_data_ref"
    redis_data_conn.delete(queue_ref_key)

    images = []
    for ev in s.node.walk_events(wait=False, include_filter="lima"):
        if ev.type == ev.type.NEW_DATA:
            images.extend(ev.data.data)
    assert len(images) == 0


def test_ttl_on_data_node(beacon, redis_data_conn, enable_ttl):
    redis_data_conn.delete("testing")
    node = DataNode("test", "testing", create=True)
    node.set_ttl()
    assert redis_data_conn.ttl("testing") == enable_ttl
    del node
    assert redis_data_conn.ttl("testing") == enable_ttl

    redis_data_conn.delete("testing")
    node = DataNode("test", "testing", create=True)
    assert redis_data_conn.ttl("testing") == -1
    del node
    assert redis_data_conn.ttl("testing") == enable_ttl


def test_ttl_setter(session, capsys, enable_ttl):
    heater = getattr(setup_globals, "heater")
    diode = getattr(setup_globals, "diode")
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    s = scans.loopscan(1, .1, heater, diode, run=False)
    out, err = capsys.readouterr()
    assert err == ""


def test_walk_after_nodes_disappeared(session):
    detector = session.env_dict["diode"]
    s = scans.loopscan(1, 0.1, detector)
    session_db_name = session.name
    scan_db_name = s.node.db_name

    def count(session=True, nodes=False, wait=True):
        # Count nodes/events when walking on session/scan node
        n = 0
        if session:
            node = get_session_node(session_db_name)
        else:
            node = get_node(scan_db_name)
        if node is None:
            return 0
        if nodes:
            it = node.walk(wait=wait)
        else:
            it = node.walk_events()
        # Stop iterating if we don't get a now
        # event after x seconds
        while True:
            try:
                with gevent.Timeout(2):
                    next(it)
                    n += 1
                    gevent.sleep()
            except (StopIteration, gevent.Timeout, gevent.GreenletExit) as e:
                print(f"Walk ended due to {e.__class__.__name__} '{e}'")
                break
        return n

    def validate_count(nnodes, nevents):
        params = itertools.product(*[[True, False]] * 3)
        for session, nodes, wait in params:
            if nodes:
                nexpected = nnodes
            else:
                nexpected = nevents
            if not session:
                # The scan does not have the NEW_NODE events for
                # the scan node and its parents
                nexpected = max(nexpected - nroot - 1, 0)
            n = count(session=session, nodes=nodes, wait=wait)
            assert n == nexpected

    # Validate counting when all nodes are still present
    nroot = len(session.scan_saving._db_path_keys) - 1
    nnodes = nroot + 6  # + scan, master, epoch, elapsed, controller, diode
    nevents = nnodes + 5  # + 3 x data + 1 x end + 1 x prepared
    validate_count(nnodes, nevents)

    # Scan incomplete
    names = s.node.search_redis(s.node.db_name + ":*")
    keep_suffix = ["_data", "_children_list"]
    for db_name in names:
        if not any(db_name.endswith(s) for s in keep_suffix):
            s.node.connection.delete(db_name)
    names = list(s.node.search_redis(s.node.db_name + "*"))

    nnodes = nroot + 1
    nevents = nnodes + 2
    validate_count(nnodes, nevents)

    # Scan missing
    s.node.connection.delete(s.node.db_name)
    nnodes = nevents = nroot
    validate_count(nnodes, nevents)


def test_children_timing(beacon, session):
    diode2 = session.env_dict["diode2"]

    def walker(db_name):
        # print("LISTENING TO", scan_node.db_name)
        scan_node = get_node(db_name)
        for event_type, node, event_data in scan_node.walk_events():
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

    g = gevent.spawn(walker, s.node.db_name)
    # print("BEFORE RUN", list([n.db_name for n in s.node.children()]))
    s.run()
    # print("AFTER RUN", list([n.db_name for n in s.node.children()]))

    g.kill()


def test_scan_end_timing(
    session, scan_meta, dummy_acq_master, dummy_acq_device, mocker
):
    scan_meta.clear()

    # Get controllers
    chain = AcquisitionChain()
    master = dummy_acq_master.get(None, name="master", npoints=1)
    device = dummy_acq_device.get(None, name="device", npoints=1)

    def side_effect(timing):
        if timing == device.META_TIMING.END:
            # this sleep is the point of the test...
            # delay the filling of scan_info
            gevent.sleep(.2)
            return {"state": "slow"}
        else:
            return None

    device.get_acquisition_metadata = mocker.Mock(side_effect=side_effect)

    chain.add(master, device)

    scan = Scan(chain, "test", save=False, scan_info={"instrument": {"some": "text"}})

    event = gevent.event.Event()

    def g(db_name):
        scan_node = get_node(db_name)
        parent = scan_node.parent
        event.set()
        first_index = int(time.time() * 1000)
        first_index -= 100  # subsctract 100ms
        # Can't use **walk_on_new_events** because
        # in this test we force to create nodes before starting scan
        # we will use **walk_event** with current time passed 100ms
        # which is equivalent to **walk_on_new_events** if we have started it
        # 100ms before.
        dummy_node = None
        for event_type, node, event_data in parent.walk_events(first_index=first_index):
            if event_type == event_type.END_SCAN:
                assert dummy_node.info.get("state") == "slow"
                assert node.info.get("instrument")["some"] == "text"
                break
            elif event_type == event_type.NEW_NODE:
                if node.name == "device":
                    dummy_node = node
                    assert dummy_node.info.get("state") is None

    # force existence of scan node before starting the scan
    scan._prepare_node()

    gg = gevent.spawn(g, scan.node.db_name)
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

    for node in s.node.walk(wait=False):
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
        for node in session_node.walk(stop_handler=stop_handler):
            pass

    stop_handler = DataStreamReaderStopHandler()
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
        for node in session_node.walk(stop_handler=stop_handler):
            event.set()

    stop_handler = DataStreamReaderStopHandler()
    task = gevent.spawn(spawn_walk, stop_handler)

    diode = session.env_dict["diode"]
    scans.loopscan(1, 0, diode, save=False)

    with gevent.Timeout(1.):
        event.wait()

    stop_handler.stop()
    with gevent.Timeout(1.):
        task.get()


def _count_node_events(
    beforestart,
    session,
    db_name,
    node_type=None,
    include_filter=None,
    count_nodes=False,
    wait=True,
    overhead=0,
):
    """
    :param bool beforestart: start listening to events before the scan starts
    :param session:
    :param str db_name: Redis node to listen to
    :param str node_type:
    :param str include_filter:
    :param bool count_nodes: count nodes insted of events
    :param bool wait: only applies when `beforestart == False`
    :param num overhead: per event
    :returns dict or list, int: events or nodes, number of detectors in scan
    """
    # Show streaming logs when test fails
    l = logging.getLogger("bliss.config.streaming")
    l.setLevel(logging.DEBUG)

    if beforestart:
        wait = True

    # Make sure the controller names are different
    names = ["diode", "thermo_sample", "sim_ct_gauss"]
    nchannels = len(names)
    detectors = [session.env_dict[d] for d in names]

    s = scans.sct(0.1, *detectors, run=not beforestart, save=False)
    nmasters = 2
    nlistenroot = len(db_name.split(":"))
    nodes = []

    def process_node(n):
        """Count nodes and check order
        """
        node = n.db_name
        error_msg = f"Node '{node}' already received"
        assert node not in nodes, error_msg
        nodes.append(node)

        if not include_filter:
            parent = n.parent.db_name
            if len(parent.split(":")) > nlistenroot:
                error_msg = f"Child node '{node}' before parent node '{parent}'"
                assert parent in nodes, error_msg

    # Function to count events or nodes
    if count_nodes:
        result = nodes
        process_event = process_node
    else:
        result = OrderedDict()
        nodes_with_event = set()
        prepared_scan_received = False
        end_scan_recieved = False

        def process_event(ev):
            """Count events and check order
            """
            nonlocal end_scan_recieved
            nonlocal prepared_scan_received
            e, n, d = ev
            node = n.db_name

            # Make sure the END_SCAN event (if any) is the last event
            error_msg = (
                f"Event '{e.name}' of '{node}' arrived after the 'END_SCAN' event"
            )
            assert not end_scan_recieved, error_msg

            # Verify event order
            if e == e.NEW_NODE:
                error_msg = f"NEW_NODE not the first event of '{node}'"
                assert node not in nodes_with_event, error_msg

                error_msg = f"Event '{e.name}' of '{node}' arrived after the 'PREPARED_SCAN' event"
                assert not prepared_scan_received, error_msg
            elif e == e.PREPARED_SCAN:
                error_msg = (
                    f"Event '{e.name}' of '{node}' arrived after the 'NEW_DATA' event"
                )
                assert node not in result.get("NEW_DATA", []), error_msg

            # Process event
            if e == e.NEW_NODE:
                process_node(n)
            elif e == e.END_SCAN:
                end_scan_recieved = True
            elif e == e.PREPARED_SCAN:
                prepared_scan_received = True

            nodes_with_event.add(node)
            result.setdefault(e.name, []).append(node)

    startlistening_event = gevent.event.Event()
    startlistening_event.clear()

    def walk():
        """Stops walking if no event has been received for x seconds
        """
        node = datanode_factory(
            db_name, node_type=node_type, on_not_state="instantiate"
        )
        if count_nodes:
            evgen = node.walk(
                include_filter=include_filter,
                wait=wait,
                started_event=startlistening_event,
            )
        else:
            evgen = node.walk_events(
                include_filter=include_filter,
                wait=wait,
                started_event=startlistening_event,
            )
        while True:
            try:
                with gevent.Timeout(overhead + 2):
                    ev = next(evgen)
                    process_event(ev)
                    gevent.sleep(overhead)
            except (StopIteration, gevent.Timeout, gevent.GreenletExit) as e:
                print(f"Walk ended due to {e.__class__.__name__} '{e}'")
                break

    # Walk the node and run the scan (if not already done)
    walk_greenlet = gevent.spawn(walk)
    try:
        with gevent.Timeout(10):
            startlistening_event.wait()
        # We are listening to the node now
        if beforestart:
            # Scan did not run yet
            scan_greenlet = gevent.spawn(s.run)
            try:
                scan_greenlet.get(timeout=60)
            finally:
                scan_greenlet.kill()
    finally:
        try:
            walk_greenlet.get(timeout=60)
        finally:
            walk_greenlet.kill()

    return result, nmasters, nchannels


def _count_nodes(*args, **kw):
    return _count_node_events(*args, **kw, count_nodes=True)


def filterepoch(node):
    return node.name == "timer:epoch"


_count_parameters = itertools.product(
    [True, False], [True, False], [None, "scan", "channel", filterepoch]
)
_count_parameters = [
    (beforestart, wait, include_filter)
    for beforestart, wait, include_filter in _count_parameters
    if not beforestart or wait
]


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_session_node(beforestart, wait, include_filter, session):
    events, nmasters, nchannels = _count_node_events(
        beforestart, session, session.name, include_filter=include_filter, wait=wait
    )
    if include_filter == "scan":
        assert list(events.keys()) == ["NEW_NODE", "PREPARED_SCAN", "END_SCAN"]
    elif include_filter == "channel":
        # New node events: epoch, elapsed_time, n x detector
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == nmasters + nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
    elif callable(include_filter):
        # New node events: epoch
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == 1
        assert len(events["NEW_DATA"]) == 1
    else:
        # New node events: root nodes, scan, scan master (timer),
        #                  epoch, elapsed_time, n  x (controller, detector)
        assert list(events.keys()) == [
            "NEW_NODE",
            "PREPARED_SCAN",
            "NEW_DATA",
            "END_SCAN",
        ]
        # One less because the NEW_NODE event for session.name is
        # not emitted on node session.name
        nroot = len(session.scan_saving._db_path_keys) - 1
        assert len(events["NEW_NODE"]) == nroot + 2 + nmasters + 2 * nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
        assert len(events["PREPARED_SCAN"]) == 1
        assert len(events["END_SCAN"]) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_session_node(beforestart, wait, include_filter, session):
    nodes, nmasters, nchannels = _count_nodes(
        beforestart, session, session.name, include_filter=include_filter, wait=wait
    )
    if include_filter == "scan":
        # Nodes: scan
        assert len(nodes) == 1
    elif include_filter == "channel":
        # Nodes: epoch, elapsed_time, n x detectors
        assert len(nodes) == nmasters + nchannels
    elif callable(include_filter):
        # Nodes: epoch
        assert len(nodes) == 1
    else:
        # Nodes: root nodes, scan, scan master (timer),
        #        epoch, elapsed_time, n  x (controller, detector)
        nroot = len(session.scan_saving._db_path_keys) - 1
        assert len(nodes) == nroot + 2 + nmasters + 2 * nchannels


@pytest.mark.parametrize("beforestart", [True, False])
def test_walk_events_on_wrong_session_node(beforestart, session):
    events, nmasters, nchannels = _count_node_events(
        beforestart, session, session.name[:-1]
    )
    assert not events


@pytest.mark.parametrize("beforestart", [True, False])
def test_walk_nodes_on_wrong_session_node(beforestart, session):
    nodes, nmasters, nchannels = _count_nodes(beforestart, session, session.name[:-1])
    assert not nodes


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_dataset_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name
    events, nmasters, nchannels = _count_node_events(
        beforestart,
        session,
        db_name,
        node_type="dataset",
        include_filter=include_filter,
        wait=wait,
    )
    if include_filter == "scan":
        # New node events: scan
        assert list(events.keys()) == ["NEW_NODE", "PREPARED_SCAN", "END_SCAN"]
    elif include_filter == "channel":
        # New node events: epoch, elapsed_time, n x detector
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == nmasters + nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
    elif callable(include_filter):
        # New node events: epoch
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == 1
        assert len(events["NEW_DATA"]) == 1
    else:
        # New node events: dataset, scan master (timer), epoch,
        #                  elapsed_time, n  x (controller, detector)
        assert list(events.keys()) == [
            "NEW_NODE",
            "PREPARED_SCAN",
            "NEW_DATA",
            "END_SCAN",
        ]
        assert len(events["NEW_NODE"]) == 2 + nmasters + 2 * nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
        assert len(events["END_SCAN"]) == 1
        assert len(events["PREPARED_SCAN"]) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_dataset_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name
    nodes, nmasters, nchannels = _count_nodes(
        beforestart,
        session,
        db_name,
        node_type="dataset",
        include_filter=include_filter,
        wait=wait,
    )
    if include_filter == "scan":
        # Nodes: scan
        assert len(nodes) == 1
    elif include_filter == "channel":
        # Nodes: epoch, elapsed_time, n x detector
        assert len(nodes) == nmasters + nchannels
    elif callable(include_filter):
        # Nodes: epoch
        assert len(nodes) == 1
    else:
        # Nodes: dataset, scan master (timer), epoch,
        #        elapsed_time, n x (controller, detector)
        assert len(nodes) == 2 + nmasters + 2 * nchannels


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_scan_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct"
    events, nmasters, nchannels = _count_node_events(
        beforestart,
        session,
        db_name,
        node_type="scan",
        include_filter=include_filter,
        wait=wait,
    )
    if include_filter == "scan":
        assert list(events.keys()) == ["PREPARED_SCAN", "END_SCAN"]
    elif include_filter == "channel":
        # New node events: epoch, elapsed_time, n x detector
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == nmasters + nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
    elif callable(include_filter):
        # New node events: epoch
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == 1
        assert len(events["NEW_DATA"]) == 1
    else:
        # New node events: scan master (timer), epoch, elapsed_time,
        #                  n  x (controller, detector)
        assert list(events.keys()) == [
            "NEW_NODE",
            "PREPARED_SCAN",
            "NEW_DATA",
            "END_SCAN",
        ]
        assert len(events["NEW_NODE"]) == 1 + nmasters + 2 * nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
        assert len(events["END_SCAN"]) == 1
        assert len(events["PREPARED_SCAN"]) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_scan_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct"
    nodes, nmasters, nchannels = _count_nodes(
        beforestart,
        session,
        db_name,
        node_type="scan",
        include_filter=include_filter,
        wait=wait,
    )
    if include_filter == "scan":
        assert not nodes
    elif include_filter == "channel":
        # Nodes: epoch, elapsed_time, n x detector
        assert len(nodes) == nmasters + nchannels
    elif callable(include_filter):
        # Nodes: epoch
        assert len(nodes) == 1
    else:
        # Nodes: scan master (timer), epoch, elapsed_time,
        #        n x (controller, detector)
        assert len(nodes) == 1 + nmasters + 2 * nchannels


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_master_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct:timer"
    events, nmasters, nchannels = _count_node_events(
        beforestart, session, db_name, include_filter=include_filter, wait=wait
    )
    if include_filter == "scan":
        assert not events
    elif include_filter == "channel":
        # New node events: epoch, elapsed_time, n x detector
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == nmasters + nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels
    elif callable(include_filter):
        # New node events: epoch
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == 1
        assert len(events["NEW_DATA"]) == 1
    else:
        # New node events: epoch, elapsed_time, n x (controller, detector)
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == nmasters + 2 * nchannels
        assert len(events["NEW_DATA"]) == nmasters + nchannels


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_master_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct:timer"
    nodes, nmasters, nchannels = _count_nodes(
        beforestart, session, db_name, include_filter=include_filter, wait=wait
    )
    if include_filter == "scan":
        assert not nodes
    elif include_filter == "channel":
        # Nodes: epoch, elapsed_time, n x detector
        assert len(nodes) == nmasters + nchannels
    elif callable(include_filter):
        # Nodes: epoch
        assert len(nodes) == 1
    else:
        # Nodes: epoch, elapsed_time, n x (controller, detector)
        assert len(nodes) == nmasters + 2 * nchannels


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_controller_node(beforestart, wait, include_filter, session):
    db_name = (
        session.scan_saving.scan_parent_db_name
        + ":_1_ct:timer:simulation_diode_sampling_controller"
    )
    events, nmasters, nchannels = _count_node_events(
        beforestart, session, db_name, include_filter=include_filter, wait=wait
    )
    if include_filter == "scan":
        assert not events
    elif include_filter == "channel":
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == 1
        assert len(events["NEW_DATA"]) == 1
    elif callable(include_filter):
        assert not events
    else:
        # New node events: diode
        assert set(events.keys()) == {"NEW_NODE", "NEW_DATA"}
        assert len(events["NEW_NODE"]) == 1
        assert len(events["NEW_DATA"]) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_controller_node(beforestart, wait, include_filter, session):
    db_name = (
        session.scan_saving.scan_parent_db_name
        + ":_1_ct:timer:simulation_diode_sampling_controller"
    )
    nodes, nmasters, nchannels = _count_nodes(
        beforestart, session, db_name, include_filter=include_filter, wait=wait
    )
    if include_filter == "scan":
        assert not nodes
    elif include_filter == "channel":
        # Nodes: diode
        assert len(nodes) == 1
    elif callable(include_filter):
        assert not nodes
    else:
        # Nodes: diode
        assert len(nodes) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_masterchannel_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct:timer:elapsed_time"
    events, nmasters, nchannels = _count_node_events(
        beforestart,
        session,
        db_name,
        node_type="channel",
        include_filter=include_filter,
        wait=wait,
    )
    if include_filter == "scan":
        assert not events
    elif include_filter == "channel":
        assert set(events.keys()) == {"NEW_DATA"}
        assert len(events["NEW_DATA"]) == 1
    elif callable(include_filter):
        assert not events
    else:
        assert set(events.keys()) == {"NEW_DATA"}
        assert len(events["NEW_DATA"]) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_masterchannel_node(beforestart, wait, include_filter, session):
    db_name = session.scan_saving.scan_parent_db_name + ":_1_ct:timer:elapsed_time"
    nodes, nmasters, nchannels = _count_nodes(
        beforestart,
        session,
        db_name,
        node_type="channel",
        include_filter=include_filter,
        wait=wait,
    )
    assert not nodes


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_events_on_controllerchannel_node(
    beforestart, wait, include_filter, session
):
    db_name = (
        session.scan_saving.scan_parent_db_name
        + ":_1_ct:timer:simulation_diode_sampling_controller:diode"
    )
    events, nmasters, nchannels = _count_node_events(
        beforestart,
        session,
        db_name,
        node_type="channel",
        include_filter=include_filter,
        wait=wait,
    )
    if include_filter == "scan":
        assert not events
    elif include_filter == "channel":
        assert set(events.keys()) == {"NEW_DATA"}
        assert len(events["NEW_DATA"]) == 1
    elif callable(include_filter):
        assert not events
    else:
        assert set(events.keys()) == {"NEW_DATA"}
        assert len(events["NEW_DATA"]) == 1


@pytest.mark.parametrize("beforestart, wait, include_filter", _count_parameters)
def test_walk_nodes_on_controllerchannel_node(
    beforestart, wait, include_filter, session
):
    db_name = (
        session.scan_saving.scan_parent_db_name
        + ":_1_ct:timer:simulation_diode_sampling_controller:diode"
    )
    nodes, nmasters, nchannels = _count_nodes(
        beforestart,
        session,
        db_name,
        node_type="channel",
        include_filter=include_filter,
        wait=wait,
    )
    assert not nodes


def test_scan_numbering(default_session, beacon):
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


def test_block_size(default_session):
    npoints = 107

    def block_generator(npoints, dtype):
        """Emits npoints in blocks
        """
        _npoints = 0
        while npoints != _npoints:
            blocksize = numpy.random.randint(low=1, high=5)
            n = numpy.random.randint(low=5, high=10)
            blocksize -= max(_npoints + blocksize - npoints, 0)
            yield [numpy.full(n, _npoints + i, dtype=dtype) for i in range(blocksize)]
            _npoints += blocksize

    class myAcqDev(AcquisitionSlave):
        def __init__(self):
            class myDev:
                def __init__(self):
                    self.name = "test_def"

            super().__init__(myDev())
            channel = AcquisitionChannel("test:test", numpy.int16, (1,))
            self.channels.append(channel)
            self.data_generator = block_generator(npoints, channel.dtype)

        def prepare(self):
            pass

        def start(self):
            channel = self.channels[0]
            try:
                block = next(self.data_generator)
            except StopIteration:
                channel.emit([])
            else:
                channel.shape = block[0].shape
                if len(block) == 1:
                    channel.emit(block[0])
                else:
                    channel.emit(block)

        def stop(sef):
            pass

        def trigger(self):
            pass

    chain = AcquisitionChain()
    master = SoftwareTimerMaster(1e-6, npoints=npoints, name="timer1")
    chain.add(master, myAcqDev())
    s = Scan(chain, name="testscan")
    s.run()

    for node in s.node.walk(wait=False):
        if node.name == "test:test":
            mynode = node
            break

    full_range = numpy.arange(npoints, dtype=numpy.int16)

    # Single value
    for i in range(npoints):
        assert mynode.get(i)[0] == i
        assert mynode.get_as_array(i)[0] == i
        assert mynode[i][0] == i
    for j in range(-1, -npoints, -1):
        assert mynode[j][0] == full_range[j]

    # First value
    for j in [0, None]:
        assert mynode.get(j)[0] == 0
        assert mynode.get_as_array(j)[0] == 0
    assert mynode[0][0] == 0
    with pytest.raises(IndexError):
        mynode[None]

    # Last value
    for j in [-1, -2]:
        assert mynode.get(j)[0] == npoints - 1
        assert mynode.get_as_array(j)[0] == npoints - 1
    assert mynode[-1][0] == npoints - 1

    # Range
    for i in range(npoints):
        j0 = max(i - 1, 0)  # could start from 0 but speedup
        for j in range(j0, npoints):
            expected = full_range[i : j + 1]
            arr = numpy.array([x[0] for x in mynode.get(i, j)])
            if expected.size:
                assert arr.dtype == numpy.int16
            assert numpy.array_equal(arr, expected)
            arr = mynode.get_as_array(i, j)[:, 0]
            if expected.size:
                assert arr.dtype == numpy.int16
            assert numpy.array_equal(arr, expected)
    for i in range(0, npoints):
        for j in range(i, npoints):
            expected = full_range[i:j]
            arr = numpy.array([x[0] for x in mynode[i:j]])
            assert numpy.array_equal(arr, expected)
    for i in range(-1, -npoints, -1):
        for j in range(i, 0):
            expected = full_range[i:j]
            arr = numpy.array([x[0] for x in mynode[i:j]])
            assert numpy.array_equal(arr, expected)

    # Full range
    for i in [0, -1, None]:
        for j in [-1, -2]:
            arr = numpy.array([x[0] for x in mynode.get(i, j)])
            assert arr.dtype == numpy.int16
            assert numpy.array_equal(arr, full_range)
            arr = mynode.get_as_array(i, j)[:, 0]
            assert arr.dtype == numpy.int16
            assert numpy.array_equal(arr, full_range)
    for idx in [slice(None, None), slice(0, None)]:
        arr = numpy.array([x[0] for x in mynode[idx]])
        assert arr.dtype == numpy.int16
        assert numpy.array_equal(arr, full_range)

    # Remove the first block
    idx, raw = mynode._queue.range(count=1)[0]
    ndel = ChannelDataEvent.decode_npoints(raw)
    nleft = npoints - ndel
    mynode._queue.remove(idx)

    # Starting index inside the removed block
    for i in range(ndel):
        # Single value
        assert mynode.get(i) is None
        with pytest.raises(IndexError):
            mynode[i]

        # Slice with open end
        if i == 0:
            assert len(mynode.get_as_array(i, -1)) == nleft
        else:
            with pytest.raises(IndexError):
                mynode.get_as_array(i, -1)
        with pytest.raises(IndexError):
            mynode[i:]

        # Slice with closed end
        for add in range(3):
            with pytest.raises(IndexError):
                mynode.get_as_array(i, i + add)
            with pytest.raises(IndexError):
                mynode[i : i + add + 1]


def test_get_last_saved_scan(session):
    session_node = get_session_node(session.name)
    detectors = (session.env_dict["diode"],)

    node = get_last_saved_scan(session_node)
    assert node is None

    s = scans.sct(0.1, *detectors)
    node = get_last_saved_scan(session_node)
    assert s.node.db_name == node.db_name

    scans.ct(0.1, *detectors)
    node = get_last_saved_scan(session_node)
    assert s.node.db_name == node.db_name

    s = scans.sct(0.1, *detectors)
    node = get_last_saved_scan(session_node)
    assert s.node.db_name == node.db_name


def test_datanode_factory(beacon):
    info = {"var1": 10}

    def func_create():
        node = datanode_factory(
            "test1", node_type="testing", info=info, create_not_state=True
        )
        assert node.type == "testing"
        assert node.info.get("var1") == 10

    glts = [gevent.spawn(func_create) for _ in range(100)]
    gevent.joinall(glts, raise_error=True)

    def func_not_create():
        node = datanode_factory(
            "test2", node_type="testing", info=info, create_not_state=False
        )
        assert node.type == "testing"
        assert node.info.get("var1") == 10

    glts = [gevent.spawn(func_not_create) for _ in range(100)]
    gevent.joinall(glts, raise_error=True)


def test_filter_nodes(session):
    # Fill Redis with scan data
    session_node = get_session_node(session.name)
    detectors = (session.env_dict["diode"],)
    nscans = 2
    for _ in range(nscans):
        scans.sct(0.1, *detectors)

    # Check the number of expected keys
    db_names = list(session_node.search_redis("*"))
    nroot = len(session.scan_saving._db_path_keys)
    keys_per_channel = 3
    keys_per_container = 2
    streams_per_scan = 2
    keys_per_scan = streams_per_scan + 3
    containers_per_scan = 2  # master, controller
    channels_per_scan = 3  # epoch, elapsed, diode
    keys_per_scan += (
        containers_per_scan * keys_per_container + channels_per_scan * keys_per_channel
    )
    nkeys = nroot * keys_per_container + nscans * keys_per_scan
    assert len(db_names) == nkeys

    # Get all nodes
    nodes_per_scan = 1 + containers_per_scan + channels_per_scan
    nnodes = nroot + nscans * nodes_per_scan
    nodes = [session_node] + list(session_node.walk(wait=False))
    assert len(nodes) == nnodes
    db_names = [n.db_name for n in nodes]

    # Check node filtering
    kw = {"include_filter": "scan"}
    fnodes = list(get_filtered_nodes(*db_names, **kw))
    assert len(fnodes) == nscans

    kw = {"include_filter": "channel"}
    fnodes = list(get_filtered_nodes(*db_names, **kw))
    assert len(fnodes) == nscans * channels_per_scan

    kw = {"recursive_exclude": "scan", "include_filter": "channel"}
    fnodes = list(get_filtered_nodes(*db_names, **kw))
    assert len(fnodes) == 0

    kw = {"recursive_exclude": "scan", "strict_recursive_exclude": True}
    fnodes = list(get_filtered_nodes(*db_names, **kw))
    assert len(fnodes) == nroot

    kw = {"recursive_exclude": "scan", "strict_recursive_exclude": False}
    fnodes = list(get_filtered_nodes(*db_names, **kw))
    assert len(fnodes) == nroot + nscans

    kw = {
        "include_filter": "scan",
        "recursive_exclude": "scan",
        "strict_recursive_exclude": False,
    }
    fnodes = list(get_filtered_nodes(*db_names, **kw))
    assert len(fnodes) == nscans


def _filter_walk_get_nodes(walk_func, wait=False, timeout=2, **kw):
    if wait:
        with pytest.raises(gevent.Timeout):
            with gevent.Timeout(timeout):
                for node in walk_func(wait=True, **kw):
                    try:
                        yield node.db_name
                    except AttributeError:
                        yield node.node.db_name
    else:
        for node in walk_func(wait=False, **kw):
            try:
                yield node.db_name
            except AttributeError:
                yield node.node.db_name


def test_walk_nodes_filter(session):
    # Fill Redis with scan data
    session_node = get_session_node(session.name)
    detectors = (session.env_dict["diode"],)
    nscans = 4
    scan_db_names = [scans.sct(0.1, *detectors).node.db_name for _ in range(nscans)]

    # For counting
    nroot = len(session.scan_saving._db_path_keys) - 1  # -1 for the session node
    containers_per_scan = 2  # master, controller
    channels_per_scan = 3  # epoch, elapsed, diode

    # Walk all nodes:
    kw = {}
    nodes_per_scan = 1 + containers_per_scan + channels_per_scan
    nnodes = nroot + nscans * nodes_per_scan
    db_names = list(_filter_walk_get_nodes(session_node.walk, wait=False, **kw))
    assert len(db_names) == nnodes
    assert set(scan_db_names).issubset(db_names)
    db_names = list(_filter_walk_get_nodes(session_node.walk, wait=True, **kw))
    assert len(db_names) == nnodes
    assert set(scan_db_names).issubset(db_names)

    # Walk all scan nodes:
    kw = {"include_filter": "scan"}
    for a, b in itertools.product((None, "scan"), (None, "scan")):
        kw = {
            "include_filter": "scan",
            "exclude_existing_children": a,
            "exclude_children": b,
        }
        db_names = list(_filter_walk_get_nodes(session_node.walk, wait=False, **kw))
        assert db_names == scan_db_names
        db_names = list(_filter_walk_get_nodes(session_node.walk, wait=True, **kw))
        assert db_names == scan_db_names


def test_walk_new_nodes_filter(session):
    # Fill Redis with scan data
    session_node = get_session_node(session.name)
    detectors = (session.env_dict["diode"],)
    nscans = 4
    scan_db_names = [scans.sct(0.1, *detectors).node.db_name for _ in range(nscans)]

    # Walk all nodes:
    kw = {}
    db_names = list(
        _filter_walk_get_nodes(
            session_node.walk_from_last, wait=False, include_last=True, **kw
        )
    )
    assert db_names
    db_names = list(
        _filter_walk_get_nodes(
            session_node.walk_from_last, wait=True, include_last=True, **kw
        )
    )
    assert db_names
    db_names = list(
        _filter_walk_get_nodes(
            session_node.walk_from_last, wait=False, include_last=False, **kw
        )
    )
    assert not db_names
    db_names = list(
        _filter_walk_get_nodes(
            session_node.walk_from_last, wait=True, include_last=False, **kw
        )
    )
    assert not db_names

    # Walk all scan nodes:
    kw = {"include_filter": "scan"}
    for a, b in itertools.product((None, "scan"), (None, "scan")):
        kw = {
            "include_filter": "scan",
            "exclude_existing_children": a,
            "exclude_children": b,
        }
        db_names = list(
            _filter_walk_get_nodes(
                session_node.walk_from_last, wait=False, include_last=True, **kw
            )
        )
        assert db_names == [scan_db_names[-1]]
        db_names = list(
            _filter_walk_get_nodes(
                session_node.walk_from_last, wait=True, include_last=True, **kw
            )
        )
        assert db_names == [scan_db_names[-1]]
        db_names = list(
            _filter_walk_get_nodes(
                session_node.walk_from_last, wait=False, include_last=False, **kw
            )
        )
        assert not db_names
        db_names = list(
            _filter_walk_get_nodes(
                session_node.walk_from_last, wait=True, include_last=False, **kw
            )
        )
        assert not db_names


def test_walk_events_filter(session):
    # Fill Redis with scan data
    session_node = get_session_node(session.name)
    detectors = (session.env_dict["diode"],)
    nscans = 4
    scan_db_names = [scans.sct(0.1, *detectors).node.db_name for _ in range(nscans)]

    # For counting
    nroot = len(session.scan_saving._db_path_keys) - 1  # -1 for the session node
    containers_per_scan = 2  # master, controller
    channels_per_scan = 3  # epoch, elapsed, diode

    # Walk all events:
    nodes_per_scan = 1 + containers_per_scan + channels_per_scan
    nevents = nroot + nscans * nodes_per_scan  # NEW_NODE
    nevents += nscans * channels_per_scan  # NEW_DATA
    nevents += nscans  # END_SCAN
    nevents += nscans  # PREPARED_SCAN
    db_names = list(_filter_walk_get_nodes(session_node.walk_events, wait=False))
    assert len(db_names) == nevents
    assert set(scan_db_names).issubset(db_names)

    # Walk all scan events:
    kw = {"include_filter": "scan"}
    nevents = 3 * nscans  # NEW_NODE + PREPARED + END_SCAN
    for a, b in itertools.product((None, "scan"), (None, "scan")):
        kw = {
            "include_filter": "scan",
            "exclude_existing_children": a,
            "exclude_children": b,
        }
        db_names = list(
            _filter_walk_get_nodes(session_node.walk_events, wait=False, **kw)
        )
        assert len(db_names) == nevents, kw
        assert set(db_names) == set(scan_db_names), kw
        db_names = list(
            _filter_walk_get_nodes(session_node.walk_events, wait=True, **kw)
        )
        assert len(db_names) == nevents, kw
        assert set(db_names) == set(scan_db_names), kw


def test_walk_new_events_filter(session):
    # Fill Redis with scan data
    session_node = get_session_node(session.name)
    detectors = (session.env_dict["diode"],)
    nscans = 4
    for _ in range(nscans):
        scans.sct(0.1, *detectors).node.db_name

    # TODO: this has always failed. We get all the NEW_DATA events, not
    #       just the new ones. This is because at the start we subscribe
    #       to all *_data streams from 0 (unless filtered out explicitely).
    #       This is done because those streams are position indexed, not time indexed.
    #
    # Walk all events:
    # db_names = list(_filter_walk_get_nodes(session_node.walk_on_new_events, wait=False))
    # assert not db_names
    # db_names = list(_filter_walk_get_nodes(session_node.walk_on_new_events, wait=True))
    # assert not db_names

    # Walk all scan events:
    for a, b in itertools.product((None, "scan"), (None, "scan")):
        kw = {
            "include_filter": "scan",
            "exclude_existing_children": a,
            "exclude_children": b,
        }
        db_names = list(
            _filter_walk_get_nodes(session_node.walk_on_new_events, wait=False, **kw)
        )
        assert not db_names, kw
        db_names = list(
            _filter_walk_get_nodes(session_node.walk_on_new_events, wait=True, **kw)
        )
        assert not db_names, kw
