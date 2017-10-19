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

    def new_scan(*args):
      print 'new', args
    def scan_data(*args):
      print 'data', args
    def scan_end(*args):
      print 'end', args
    assert scan_saving.session == 'test_session'
    session_watcher = gevent.spawn(watch_session_scans, scan_saving.session, new_scan, scan_data, scan_end)

    master = SoftwarePositionTriggerMaster(m1, 0, 1, 10, time=1)
    end_pos = master._calculate_undershoot(1, end=True)
    acq_dev = SamplingCounterAcquisitionDevice(counter, 0.01, npoints=10)

    chain = AcquisitionChain()
    chain.add(master, acq_dev)
    scan = Scan(chain, parent=scan_saving.get_parent_node())
    scan.run()

    data = get_data(scan)

    assert pytest.approx(m1.position(), end_pos)    
    assert len(data[counter.name]) == 10
    numpy.testing.assert_allclose(data[m1.name], master._positions, atol=1e-1)

    

