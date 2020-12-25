# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import pytest
import numpy
import re

from bliss.scanning.group import Sequence, Group, ScanSequenceError
from bliss.common import scans
from bliss.data.node import get_node, get_or_create_node
from bliss.data.nodes.node_ref_channel import NodeRefChannel
from bliss.data.nodes.scan import ScanNode
from bliss.scanning.chain import AcquisitionChannel
from bliss.data.node import get_session_node
from bliss import current_session
from bliss.scanning.scan import ScanState


def test_sequence_terminated_scans(session):
    diode = session.config.get("diode")
    seq = Sequence()
    with seq.sequence_context() as seq_context:
        seq_context.add(scans.loopscan(3, .1, diode))
        seq_context.add(scans.loopscan(3, .2, diode))

    n = get_node(seq.node.db_name + ":GroupingMaster:scans")
    assert isinstance(n, NodeRefChannel)
    assert len(n) == 2
    grouped_scans = n.get(0, -1)
    assert len(grouped_scans) == 2
    for s in grouped_scans:
        assert isinstance(s, ScanNode)

    assert len(get_node(seq.node.db_name + ":GroupingMaster:scan_numbers")) == 2

    assert seq.node.info["title"] == "sequence_of_scans"


def test_sequence_future_scans(session):
    diode = session.config.get("diode")
    seq = Sequence()
    with seq.sequence_context() as seq_context:
        s1 = scans.loopscan(3, .1, diode, run=False)
        seq_context.add(s1)
        s1.run()
        s2 = scans.loopscan(3, .2, diode, run=False)
        seq_context.add_and_run(s2)

    n = get_node(seq.node.db_name + ":GroupingMaster:scans")
    grouped_scans = n.get(0, -1)
    assert len(grouped_scans) == 2
    for s in grouped_scans:
        assert isinstance(s, ScanNode)
    assert grouped_scans[0].info["scan_nb"] == s1.scan_info["scan_nb"]
    assert grouped_scans[1].info["scan_nb"] == s2.scan_info["scan_nb"]

    assert all(
        get_node(seq.node.db_name + ":GroupingMaster:scan_numbers").get(0, -1)
        == [s1.scan_info["scan_nb"], s2.scan_info["scan_nb"]]
    )


def test_sequence_async_scans(session):
    diode = session.config.get("diode")
    sim_ct_gauss = session.config.get("sim_ct_gauss")
    robz = session.config.get("robz")

    # test that wait_all_subscans works
    seq = Sequence()
    with seq.sequence_context() as seq_context:
        s1 = scans.loopscan(20, .1, diode, run=False)
        s2 = scans.ascan(robz, 0, 1, 20, .1, sim_ct_gauss, run=False)
        seq_context.add(s1)
        seq_context.add(s2)
        g1 = gevent.spawn(s1.run)
        g2 = gevent.spawn(s2.run)

        gevent.sleep(0)
        seq_context.wait_all_subscans()

    gevent.joinall([g1, g2], raise_error=True)

    # test that gevent.join is sufficent
    seq = Sequence()
    with seq.sequence_context() as seq_context:
        s1 = scans.loopscan(20, .1, diode, run=False)
        s2 = scans.ascan(robz, 0, 1, 20, .1, sim_ct_gauss, run=False)
        seq_context.add(s1)
        seq_context.add(s2)
        g1 = gevent.spawn(s1.run)
        g2 = gevent.spawn(s2.run)

        gevent.joinall([g1, g2], raise_error=True)


def test_sequence_non_started_scans_in_seq(session):
    diode = session.config.get("diode")

    with pytest.raises(ScanSequenceError):
        seq = Sequence()
        with seq.sequence_context() as seq_context:
            s0 = scans.loopscan(1, .1, diode)
            seq_context.add(s0)
            s1 = scans.loopscan(20, .1, diode, run=False)
            seq_context.add(s1)


def test_empty_group(session, capsys):
    s = Group()
    out, err = capsys.readouterr()
    assert err == ""


def test_sequence_empty_in_seq(session):
    diode = session.config.get("diode")
    seq = Sequence()
    with seq.sequence_context() as seq_context:
        pass

    with pytest.raises(ScanSequenceError):
        seq = Sequence()
        with seq.sequence_context() as seq_context:
            s1 = scans.loopscan(20, .1, diode, run=False)
            seq_context.add(s1)


def test_sequence_custom_channel(session):
    diode = session.config.get("diode")
    seq = Sequence(scan_info={"something": "else"})
    seq.add_custom_channel(AcquisitionChannel("mychannel", numpy.float, ()))
    with seq.sequence_context() as seq_context:
        s1 = scans.loopscan(3, .1, diode, run=False)
        seq_context.add(s1)
        seq.custom_channels["mychannel"].emit(1.1)
        s1.run()
        seq.custom_channels["mychannel"].emit([2.2, 3.3])
        s2 = scans.loopscan(3, .05, diode)
        seq_context.add(s2)
        seq.custom_channels["mychannel"].emit([4.4])

    nodes = [node.db_name for node in seq.node.walk(wait=False)]

    assert seq.node.db_name + ":GroupingMaster:custom_channels" in nodes
    assert seq.node.db_name + ":GroupingMaster:custom_channels:mychannel" in nodes
    assert all(
        get_node(seq.node.db_name + ":GroupingMaster:custom_channels:mychannel").get(
            0, -1
        )
        == [1.1, 2.2, 3.3, 4.4]
    )

    n = get_node(seq.node.db_name + ":GroupingMaster:scans")
    grouped_scans = n.get(0, -1)
    assert len(grouped_scans) == 2
    for s in grouped_scans:
        assert isinstance(s, ScanNode)
    assert grouped_scans[0].info["scan_nb"] == s1.scan_info["scan_nb"]
    assert grouped_scans[1].info["scan_nb"] == s2.scan_info["scan_nb"]
    assert seq.node.info["something"] == "else"


def test_sequence_add_and_run(session):
    diode = session.config.get("diode")

    seq = Sequence()
    with seq.sequence_context() as seq_context:
        s0 = scans.loopscan(1, .1, diode, run=False)
        seq_context.add_and_run(s0)

    with pytest.raises(ScanSequenceError):
        seq = Sequence()
        with seq.sequence_context() as seq_context:
            s0 = scans.loopscan(1, .1, diode, run=False)
            seq_context.add_and_run(s0)
            s1 = scans.loopscan(1, .1, diode)
            seq_context.add_and_run(s1)


def test_sequence_group(session):
    diode = session.config.get("diode")
    s1 = scans.loopscan(3, .1, diode)
    s2 = scans.loopscan(3, .05, diode)

    g = Group(s1, s2, scan_info={"one": "two"})

    n = get_node(g.node.db_name + ":GroupingMaster:scans")
    grouped_scans = n.get(0, -1)
    assert len(grouped_scans) == 2
    assert grouped_scans[0].info["scan_nb"] == s1.scan_info["scan_nb"]
    assert grouped_scans[1].info["scan_nb"] == s2.scan_info["scan_nb"]
    assert g.node.info["one"] == "two"
    assert g.node.info["title"] == "group_of_scans"
    assert len(get_node(g.node.db_name + ":GroupingMaster:scan_numbers")) == 2

    g2 = Group(s1.node, s2.node)

    n = get_node(g2.node.db_name + ":GroupingMaster:scans")
    grouped_scans = n.get(0, -1)
    assert len(grouped_scans) == 2
    assert grouped_scans[0].info["scan_nb"] == s1.scan_info["scan_nb"]
    assert grouped_scans[1].info["scan_nb"] == s2.scan_info["scan_nb"]

    g2 = Group(s1.scan_info["scan_nb"], s2.scan_info["scan_nb"])
    n = get_node(g2.node.db_name + ":GroupingMaster:scans")
    grouped_scans = n.get(0, -1)
    assert len(grouped_scans) == 2
    assert grouped_scans[0].info["scan_nb"] == s1.scan_info["scan_nb"]
    assert grouped_scans[1].info["scan_nb"] == s2.scan_info["scan_nb"]


def test_sequence_invalid_group(session):
    diode = session.config.get("diode")
    s1 = scans.loopscan(3, .1, diode)
    s2 = scans.loopscan(3, .05, diode, run=False)

    with pytest.raises(ScanSequenceError):
        g = Group(s1, s2)

    n = get_or_create_node("bla:bla:bla")
    with pytest.raises(ScanSequenceError):
        g = Group(s1, n)

    with pytest.raises(ScanSequenceError):
        g = Group(s1, 158453)


def test_sequence_ttl(session, enable_ttl):
    diode = session.config.get("diode")
    s1 = scans.loopscan(3, .1, diode)
    s1_ttl1 = s1.node.connection.ttl(s1.node.db_name)

    gevent.sleep(2)

    seq = Sequence()
    with seq.sequence_context() as seq_context:
        seq_context.add(scans.loopscan(3, .1, diode))
        s1_ttl2 = s1.node.connection.ttl(s1.node.db_name)
        seq_context.add(s1)
    s1_ttl3 = s1.node.connection.ttl(s1.node.db_name)

    assert s1_ttl1 > s1_ttl2
    assert s1_ttl2 < s1_ttl3


def test_sequence_events(session):
    diode = session.config.get("diode")
    robz = session.config.get("robz")

    def my_seq(diode, robz):
        s2 = scans.loopscan(3, .1, diode)
        seq = Sequence()
        with seq.sequence_context() as seq_context:
            s0 = scans.ascan(robz, 0, .1, 3, .1, diode, run=False)
            seq_context.add(s0)
            s0.run()
            s1 = scans.dscan(robz, .1, 0, 3, .1, diode, run=False)
            seq_context.add_and_run(s1)
            seq_context.add(s2)

    event_dump = list()
    nexpectedevents = 49
    started_event = gevent.event.Event()
    finished_event = gevent.event.Event()

    def my_listener(session_node, event_dump):
        try:
            nevents = 0
            it = session_node.walk_events(started_event=started_event)
            for i, (eventtype, node, data) in enumerate(it):
                event = (
                    eventtype.name,
                    node.type,
                    re.split(r"test_sequence_events[0-9,_]*:", node.db_name)[-1],
                )
                print(len(event_dump), event)
                event_dump.append(event)
                nevents += 1
                if nevents == nexpectedevents:
                    break
        finally:
            del it  # stop DataStreamReader, don't wait for garbage collection
            finished_event.set()

    # Make sure we are listening before the scan starts
    g_lis = gevent.spawn(
        my_listener, get_session_node(current_session.name), event_dump
    )
    assert started_event.wait(timeout=5)

    # Launch the sequence of scans and wait until all END_SCAN events
    # were recieved
    g_seq = gevent.spawn(my_seq, diode, robz)
    g_seq.join()
    assert finished_event.wait(timeout=5)
    g_lis.kill()

    start_1_loopscan = event_dump.index(("NEW_NODE", "scan", "1_loopscan"))
    end_1_loopscan = event_dump.index(("END_SCAN", "scan", "1_loopscan"))
    assert start_1_loopscan != 0
    assert start_1_loopscan < end_1_loopscan

    start_2_sequence_of_scans = event_dump.index(
        ("NEW_NODE", "scan_group", "2_sequence_of_scans")
    )
    assert end_1_loopscan < start_2_sequence_of_scans

    start_3_ascan = event_dump.index(("NEW_NODE", "scan", "3_ascan"))
    assert start_2_sequence_of_scans < start_3_ascan

    sequence_event_3_ascan = event_dump.index(
        ("NEW_DATA", "channel", "2_sequence_of_scans:GroupingMaster:scan_numbers")
    )
    assert start_3_ascan < sequence_event_3_ascan

    sequence_event_3_ascan = event_dump.index(
        ("NEW_DATA", "node_ref_channel", "2_sequence_of_scans:GroupingMaster:scans")
    )
    assert start_3_ascan < sequence_event_3_ascan

    data_3_ascan = event_dump.index(("NEW_DATA", "channel", "3_ascan:axis:robz"))
    assert start_3_ascan < data_3_ascan

    end_3_ascan = event_dump.index(("END_SCAN", "scan", "3_ascan"))
    assert data_3_ascan < end_3_ascan

    start_4_dscan = event_dump.index(("NEW_NODE", "scan", "4_dscan"))
    assert end_3_ascan < start_4_dscan

    sequence_event_4_dscan = event_dump.index(
        ("NEW_DATA", "node_ref_channel", "2_sequence_of_scans:GroupingMaster:scans"),
        start_4_dscan,
    )
    assert start_4_dscan < sequence_event_4_dscan

    sequence_event_4_dscan = event_dump.index(
        ("NEW_DATA", "node_ref_channel", "2_sequence_of_scans:GroupingMaster:scans"),
        start_4_dscan,
    )
    assert start_4_dscan < sequence_event_4_dscan

    data_4_dscan = event_dump.index(("NEW_DATA", "channel", "4_dscan:axis:robz"))
    assert start_4_dscan < data_4_dscan

    end_4_dscan = event_dump.index(("END_SCAN", "scan", "4_dscan"))
    assert data_4_dscan < end_4_dscan

    end_2_sequence_of_scans = event_dump.index(
        ("END_SCAN", "scan_group", "2_sequence_of_scans")
    )
    assert sequence_event_4_dscan < end_2_sequence_of_scans


def test_group_with_killed_scan(default_session):
    diode = default_session.config.get("diode")

    def killed_scan():
        s = scans.loopscan(10, .1, diode, run=False)
        g = gevent.spawn(s.run)
        s.wait_state(ScanState.STARTING)
        g.kill()
        return s

    s1 = scans.loopscan(3, .1, diode)
    s2 = killed_scan()

    g = Group(s1, s2)

    assert g.state == ScanState.KILLED


def test_sequence_missing_events(session):
    # Test for issue #2423
    diode = session.config.get("diode")

    with gevent.Timeout(10):
        seq = Sequence()
        with pytest.raises(ScanSequenceError):
            with seq.sequence_context() as seq_context:
                # Stop publishing sequence events to check that
                # ScanSequenceError is raised upon exiting the context
                seq_context.sequence.group_acq_master.scan_queue.put(StopIteration)
                # Add a scan so that some sequence events are expected
                seq_context.add(scans.loopscan(3, .1, diode))

    with gevent.Timeout(10):
        seq = Sequence()
        with seq.sequence_context() as seq_context:
            # Stop publishing sequence events to check that
            # ScanSequenceError is raised upon exiting the context
            seq_context.sequence.group_acq_master.scan_queue.put(StopIteration)
            # Do not add scans so no sequence events are expected
