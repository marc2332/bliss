# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import numpy
import pickle as pickle
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.data.node import DataNodeContainer, _get_or_create_node
from bliss.config.settings import scan as redis_scan
from bliss.config.settings import QueueObjSetting
from bliss.data.scan import Scan as ScanNode
from bliss.data.node import get_node, DataNodeIterator, DataNode
from bliss.data.channel import ChannelDataNode


@pytest.fixture
def lima_session(beacon, scan_tmpdir, lima_simulator):
    session = beacon.get("lima_test_session")
    session.setup()
    setup_globals.SCAN_SAVING.base_path = str(scan_tmpdir)
    yield session
    session.close()


def test_parent_node(session, scan_tmpdir):
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    scan_saving.base_path = str(scan_tmpdir)
    scan_saving.template = "{date}/test"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.db_name == "test_session:%s:test" % scan_saving.date
    assert parent_node.type == "container"
    assert isinstance(parent_node, DataNodeContainer)


def test_scan_node(session, redis_data_conn, scan_tmpdir):
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 10
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, 5),
        SamplingCounterAcquisitionDevice(diode, 0.01, npoints=5),
    )

    s = Scan(chain, "test_scan", scan_info={"metadata": 42})
    assert s.name == "test_scan"
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

    with gevent.Timeout(5):
        s.run()

    assert redis_data_conn.ttl(s.node.db_name) > 0

    m0_node_db_name = s.node.db_name + ":roby"
    scan_children_node = [m0_node_db_name]
    m0_children_node = [m0_node_db_name + ":roby", m0_node_db_name + ":diode"]
    assert redis_data_conn.lrange(s.node.db_name + "_children_list", 0, -1) == [
        x.encode() for x in scan_children_node
    ]
    assert redis_data_conn.lrange(m0_node_db_name + "_children_list", 0, -1) == [
        x.encode() for x in m0_children_node
    ]

    for child_node_name in scan_children_node + m0_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0


def test_interrupted_scan(session, redis_data_conn, scan_tmpdir):
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 10
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, 5),
        SamplingCounterAcquisitionDevice(diode, 0.01, npoints=5),
    )

    s = Scan(chain, "test_scan")
    scan_task = gevent.spawn(s.run)
    gevent.sleep(0.5)
    assert pytest.raises(KeyboardInterrupt, "scan_task.kill(KeyboardInterrupt)")

    assert redis_data_conn.ttl(s.node.db_name) > 0

    m0_node_db_name = s.node.db_name + ":roby"
    scan_children_node = [m0_node_db_name]
    m0_children_node = [m0_node_db_name + ":roby", m0_node_db_name + ":diode"]

    for child_node_name in scan_children_node + m0_children_node:
        assert redis_data_conn.ttl(child_node_name) > 0


def test_scan_data_0d(session, redis_data_conn):
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan=True, save=False)

    assert s == setup_globals.SCANS[-1]
    redis_data = list(
        map(
            float,
            redis_data_conn.lrange(
                s.node.db_name + ":timer:gaussian:gaussian_data", 0, -1
            ),
        )
    )

    assert numpy.array_equal(redis_data, counter.data)

    redis_keys = set(redis_scan(session.name + "*", connection=redis_data_conn))
    session_node = get_node(session.name)
    db_names = set([n.db_name for n in DataNodeIterator(session_node).walk(wait=False)])
    assert len(db_names) > 0
    assert db_names == redis_keys.intersection(db_names)


def test_data_iterator_event(beacon, redis_data_conn, scan_tmpdir, session):
    def iterate_channel_events(scan_db_name, channels):
        for e, n in DataNodeIterator(get_node(scan_db_name)).walk_events():
            if n.type == "channel":
                channels[n.name] = n.get(0, -1)

    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    scan_saving.base_path = str(scan_tmpdir)
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity = 5
    diode = getattr(setup_globals, "diode")
    npts = 5
    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(m, 0, 1, npts),
        SamplingCounterAcquisitionDevice(diode, 0.01, npoints=npts),
    )

    s = Scan(chain, "test_scan")

    channels_data = dict()
    iteration_greenlet = gevent.spawn(
        iterate_channel_events, s.node.db_name, channels_data
    )

    s.run()

    time.sleep(0.1)
    iteration_greenlet.kill()

    assert set(("roby", "diode")) == set(channels_data.keys())
    assert len(channels_data["roby"]) == npts
    assert len(channels_data["diode"]) == npts

    x = DataNodeIterator(get_node(s.node.db_name))
    print(x)
    for n in x.walk_from_last(filter="channel", wait=False):
        assert n.get(0, -1) == channels_data[n.name]
    assert isinstance(n, ChannelDataNode)


@pytest.mark.parametrize("with_roi", [False, True], ids=["without ROI", "with ROI"])
def test_reference_with_lima(redis_data_conn, lima_session, with_roi):
    lima_sim = getattr(setup_globals, "lima_simulator")

    # Roi handling
    lima_sim.roi_counters.clear()
    if with_roi:
        lima_sim.roi_counters["myroi"] = [0, 0, 1, 1]

    timescan = scans.timescan(0.1, lima_sim, npoints=3, return_scan=True)

    session_node = get_node(lima_session.name)
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
                    if event_type == DataNodeIterator.NEW_DATA_IN_CHANNEL_EVENT:
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
