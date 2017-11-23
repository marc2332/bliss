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
import cPickle as pickle
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.data.node import DataNodeContainer
from bliss.config.settings import scan as redis_scan
from bliss.data.scan import Scan as ScanNode
from bliss.data.node import get_node, DataNodeIterator
from bliss.data.channel import ChannelDataNode

def test_parent_node(beacon):
    session = beacon.get("test_session")
    session.setup()
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    scan_saving.template="{session}/{date}/test"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.db_name == "test_session:%s:test" % scan_saving.date
    assert parent_node.type == "container"
    assert isinstance(parent_node, DataNodeContainer)

def test_scan_node(beacon, redis_data_conn):
    session = beacon.get("test_session")
    session.setup()
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity(10)
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m, 0, 1, 5), SamplingCounterAcquisitionDevice(diode, 0.01, npoints=5))

    s = Scan(chain, "test_scan", parent, { "metadata": 42 })
    assert s.name == "test_scan_1"
    assert s.root_node == parent
    assert isinstance(s.node, ScanNode) 
    assert s.node.type == "scan"
    assert s.node.db_name == s.root_node.db_name+":"+s.name
 
    scan_node_dict = redis_data_conn.hgetall(s.node.db_name)
    assert scan_node_dict.get('name') == "test_scan_1"
    assert scan_node_dict.get('db_name') == s.node.db_name
    assert scan_node_dict.get('node_type') == "scan"
    assert scan_node_dict.get('parent') == s.node.parent.db_name

    scan_info_dict = redis_data_conn.hgetall(s.node.db_name+"_info")
    assert pickle.loads(scan_info_dict['metadata']) == 42
    
    s.run()

    m0_node_db_name = s.node.db_name+":roby"
    assert redis_data_conn.lrange(s.node.db_name+"_children_list", 0, -1) == [m0_node_db_name]
    assert redis_data_conn.lrange(m0_node_db_name+"_children_list", 0, -1) == [m0_node_db_name+":roby", m0_node_db_name+":diode"]

def test_scan_data_0d(beacon, redis_data_conn):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan = True, save=False)

    redis_data = map(float, redis_data_conn.lrange(s.node.db_name+":timer:gaussian:gaussian_data", 0, -1))

    assert numpy.array_equal(redis_data, counter.data)

def test_data_iterator(beacon, redis_data_conn):
    session = beacon.get("test_session")
    redis_keys = set(redis_scan(session.name+"*", connection=redis_data_conn))
    session_node = get_node(session.name)
    db_names = set([n.db_name for n in DataNodeIterator(session_node).walk(wait=False)])
    assert len(db_names) > 0
    assert db_names == redis_keys.intersection(db_names)

def test_data_iterator_event(beacon, redis_data_conn):
    def iterate_channel_events(scan_db_name, channels):
      for e, n in DataNodeIterator(get_node(scan_db_name)).walk_events():
        if n.type == 'channel':
          channels[n.name] = n.get(0, -1)
  
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    parent = scan_saving.get_parent_node()
    m = getattr(setup_globals, "roby")
    m.velocity(10)
    diode = getattr(setup_globals, "diode")
    npts = 5
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m, 0, 1, npts), SamplingCounterAcquisitionDevice(diode, 0.01, npoints=npts))

    s = Scan(chain, "test_scan", parent)

    channels_data = dict()
    iteration_greenlet = gevent.spawn(iterate_channel_events, s.node.db_name, channels_data)

    s.run()
    
    time.sleep(0.1)
    iteration_greenlet.kill()

    assert set(('roby', 'diode')) == set(channels_data.keys())
    assert len(channels_data['roby']) == npts
    assert len(channels_data['diode']) == npts

    for n in DataNodeIterator(get_node(s.node.db_name)).walk_from_last(filter='channel', wait=False):
      assert n.get(0, -1) == channels_data[n.name]
    assert isinstance(n, ChannelDataNode) 
