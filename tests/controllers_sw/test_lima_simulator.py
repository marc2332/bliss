# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
from bliss.common.tango import DeviceProxy
from bliss.common.measurement import BaseCounter
from bliss.controllers.lima.roi import Roi
from bliss import setup_globals

def test_lima_simulator(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert simulator.camera
    assert simulator.acquisition
    assert simulator.image

    trigger_mode = simulator.acquisition.trigger_mode
    try:
        simulator.acquisition.trigger_mode = 'INTERNAL_TRIGGER_MULTI'
        assert simulator.acquisition.trigger_mode == 'INTERNAL_TRIGGER_MULTI'
        assert simulator.acquisition.trigger_mode == \
        simulator.acquisition.trigger_mode_enum.INTERNAL_TRIGGER_MULTI
    finally:
        simulator.acquisition.trigger_mode = trigger_mode

    assert isinstance(simulator.image, BaseCounter)

    assert simulator.camera.test == 'test'

def test_lima_sim_bpm(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert pytest.raises(RuntimeError, "simulator.bpm")

    assert 'bpm' not in simulator.counters._fields
    assert 'bpm' not in simulator.counter_groups._fields

def assert_lima_rois(lima_roi_counter, rois):
    roi_names = lima_roi_counter.getNames()
    raw_rois = lima_roi_counter.getRois(roi_names)

    assert set(rois.keys()) == set(roi_names)

    lima_rois = { name:Roi(*raw_rois[i*5+1:i*5+4+1], name=name)
                  for i, name in  enumerate(roi_names) }
    assert rois == lima_rois


def test_rois(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")
    rois = simulator.roi_counters

    dev_name = lima_simulator[0].lower()
    roi_dev = DeviceProxy(dev_name.replace('limaccds', 'roicounter'))

    assert len(rois) == 0

    r1 = Roi(0, 0, 100, 200)
    r2 = Roi(10, 20, 200, 500)
    r3 = Roi(20, 60, 500, 500)
    r4 = Roi(60, 20, 50, 10)

    rois['r1'] = r1
    assert_lima_rois(roi_dev, dict(r1=r1))
    rois['r2'] = r2
    assert_lima_rois(roi_dev, dict(r1=r1, r2=r2))
    rois['r3', 'r4'] = r3, r4
    assert_lima_rois(roi_dev, dict(r1=r1, r2=r2, r3=r3, r4=r4))

    assert len(rois) == 4
    assert rois['r1'] == r1
    assert rois.get('r1') == r1
    assert rois['r4', 'r1'] == [r4, r1]
    assert set(rois.keys()) == {'r1', 'r2', 'r3', 'r4'}

    with pytest.raises(KeyError):
        rois['r5']
    assert rois.get('r5') is None

    assert 'r1' in rois
    assert not 'r5' in rois

    del rois['r1']
    assert len(rois) == 3
    assert_lima_rois(roi_dev, dict(r2=r2, r3=r3, r4=r4))

    del rois['r3', 'r2']
    assert len(rois) == 1
    assert_lima_rois(roi_dev, dict(r4=r4))

    # test classic interface

    rois.set('r1', r1)
    assert len(rois) == 2
    assert_lima_rois(roi_dev, dict(r1=r1, r4=r4))

    rois.remove('r4')
    assert len(rois) == 1
    assert_lima_rois(roi_dev, dict(r1=r1))
    
def test_directories_mapping(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert simulator.directories_mapping_names == ['identity', 'fancy']
    assert simulator.current_directories_mapping == 'identity'
    assert simulator.get_mapped_path("/tmp/scans/bla") == "/tmp/scans/bla"
    
    try:
        simulator.select_directories_mapping('fancy')
        assert simulator.current_directories_mapping == 'fancy'
        assert simulator.get_mapped_path("/tmp/scans/bla") == "/tmp/fancy/bla"

        assert simulator.get_mapped_path("/data/inhouse") == "/data/inhouse"
    finally:
        simulator.select_directories_mapping('identity')

    assert pytest.raises(ValueError, \
                         "simulator.select_directories_mapping('invalid')")

def test_lima_mapping_and_saving(beacon, lima_simulator):
    session = beacon.get("test_session")
    simulator = beacon.get("lima_simulator")
    session.setup()
    scan_saving = setup_globals.SCAN_SAVING

    scan_saving.base_path="/tmp/scans"
    saving_directory = None
    try:
        simulator.select_directories_mapping('fancy')
        mapped_directory = simulator.get_mapped_path(scan_saving.get_path())
        ct = setup_globals.ct(0.1, simulator, save=True, run=False)
        mapped_directory = os.path.join(mapped_directory, ct.name)

        try:
            ct.run()
        except Exception, e:
            # this will fail because directory is not likely to exist
            saving_directory = e.args[0].desc.split("Directory :")[-1].split()[0]

    finally:
        simulator.select_directories_mapping('identity')

    # cannot use simulator.proxy.saving_directory because it is reset to ''
    assert saving_directory == mapped_directory
