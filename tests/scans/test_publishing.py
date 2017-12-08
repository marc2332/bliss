# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import numpy
import cPickle as pickle
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.data.node import DataNodeContainer
from bliss.data.scan import Scan as ScanNode
from bliss.config.conductor.client import get_default_connection

def test_parent_node(beacon):
    session = beacon.get("test_session")
    session.setup()
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    scan_saving.template="{session}/{date}/test"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.db_name == "test_session:%s:test" % scan_saving.date
    assert parent_node.type == "container"
    assert isinstance(parent_node, DataNodeContainer)

def test_scan_node(beacon):
    session = beacon.get("test_session")
    session.setup()
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    parent = scan_saving.get_parent_node()
    m0 = getattr(setup_globals, "m0")
    m0.velocity(10)
    diode = getattr(setup_globals, "diode")

    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 5), SamplingCounterAcquisitionDevice(diode, 0.01))

    s = Scan(chain, "test_scan", parent, { "metadata": 42 })
    assert s.name == "test_scan_1"
    assert s.root_node == parent
    assert isinstance(s.node, ScanNode) 
    assert s.node.type == "scan"
    assert s.node.db_name == s.root_node.db_name+":"+s.name
 
    # check redis data
    cnx = get_default_connection()
    redis_conn = cnx.get_redis_connection(db=1)

    scan_node_dict = redis_conn.hgetall(s.node.db_name)
    assert scan_node_dict.get('name') == "test_scan_1"
    assert scan_node_dict.get('db_name') == s.node.db_name
    assert scan_node_dict.get('node_type') == "scan"
    assert scan_node_dict.get('parent') == s.node.parent.db_name

    scan_info_dict = redis_conn.hgetall(s.node.db_name+"_info")
    assert pickle.loads(scan_info_dict['metadata']) == 42
    
    s.run()

    m0_node_db_name = s.node.db_name+":m0"
    assert redis_conn.lrange(s.node.db_name+"_children_list", 0, -1) == [m0_node_db_name]
    assert redis_conn.lrange(m0_node_db_name+"_children_list", 0, -1) == [m0_node_db_name+":m0", m0_node_db_name+":diode"]

def test_scan_data_0d(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan = True, save=False)

    # check redis data
    cnx = get_default_connection()
    redis_conn = cnx.get_redis_connection(db=1)

    redis_data = map(float, redis_conn.lrange(s.node.db_name+":timer:gaussian:gaussian_data", 0, -1))

    assert numpy.array_equal(redis_data, counter.data)
    
