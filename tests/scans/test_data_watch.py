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
import numpy.testing
from bliss import setup_globals
from bliss.common import event
from bliss.scanning.acquisition.motor import  SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.scan import Scan, ScanSaving
from bliss.data.scan import get_data, watch_session_scans
from bliss.scanning.chain import AcquisitionChain

def test_simple_continuous_scan_with_session_watcher(beacon):
    session = beacon.get("test_session")
    session.setup()

    m1 = getattr(setup_globals, "m1")
    counter = getattr(setup_globals, "diode")
    scan_saving = ScanSaving()
    vars = { "new_scan_cb_called": False, "scan_acq_chain": None, "scan_children":[], "scan_data":[] }

    def new_scan(scan_info, vars=vars):
      assert scan_info['session_name']==scan_saving.session
      assert scan_info['user_name']==scan_saving.user_name
      vars["scan_acq_chain"] = scan_info['acquisition_chain']
      vars["new_scan_cb_called"] = True

    def scan_new_child(scan_info, data_channel, vars=vars):
      vars["scan_children"].append(data_channel.name)

    def scan_data(type, master_name, data, vars=vars):
      assert type=='0d'
      assert master_name=='m1'
      assert data["master_channels"] == ["m1:m1"]
      vars["scan_data_m1"] = data["data"][data["master_channels"][0]]
      vars["scan_data_diode"] = data["data"]["diode:diode"]
 
    session_watcher = watch_session_scans(scan_saving.session, new_scan, scan_new_child, scan_data, wait=False)

    gevent.sleep(0.1) #wait a bit to have session watcher greenlet started

    master = SoftwarePositionTriggerMaster(m1, 0, 1, 10, time=1)
    end_pos = master._calculate_undershoot(1, end=True)
    acq_dev = SamplingCounterAcquisitionDevice(counter, 0.01, npoints=10)

    chain = AcquisitionChain()
    chain.add(master, acq_dev)
    scan = Scan(chain, parent=scan_saving.get_parent_node())
    scan.run()

    assert vars["new_scan_cb_called"]
    assert vars["scan_acq_chain"] == {'m1': {'scalars': ['diode:diode'], 'images': [], 'spectra': [], 'master': {'scalars': ['m1:m1'], 'images': [], 'spectra': []}}}
    assert numpy.allclose(vars["scan_data_m1"], master._positions, atol=1e-1)

    assert pytest.approx(m1.position(), end_pos)


def test_scan_saving(beacon):
    session = beacon.get("test_session")
    session.setup()

    scan_saving = ScanSaving()

    scan_saving.template = "{session}/toto"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.parent is not None
    assert parent_node.parent.name == scan_saving.session
    assert parent_node.parent.db_name == scan_saving.session
    assert parent_node.name == 'toto'
    assert parent_node.db_name == '%s:%s' % (scan_saving.session, 'toto')

    scan_saving.template = "toto"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.parent is not None
    assert parent_node.parent.name == scan_saving.session
    assert parent_node.parent.db_name == scan_saving.session
    assert parent_node.name == "toto"
    assert parent_node.db_name == '%s:%s' % (scan_saving.session, 'toto')

    scan_saving.template = "toto/{session}"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.parent is not None
    assert parent_node.parent.name == "toto"
    assert parent_node.parent.db_name == '%s:%s' % (scan_saving.session, 'toto')
    assert parent_node.name == scan_saving.session
    assert parent_node.db_name == '%s:%s:%s' % (scan_saving.session, 'toto',
                                                scan_saving.session)
    

