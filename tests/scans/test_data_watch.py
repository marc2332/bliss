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
import numpy.testing
from bliss import setup_globals
from bliss.common import event
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.scan import Scan, ScanSaving, ScanState
from bliss.data.scan import get_data, watch_session_scans
from bliss.scanning.chain import AcquisitionChain
from bliss.common.standard import info


@pytest.fixture
def scan_saving():
    ss = ScanSaving("test")
    prev_template = ss.template
    yield ss
    ss.template = prev_template


def test_scan_saving(session, scan_saving):
    scan_saving.base_path = "/tmp"
    scan_saving.template = "{session}/toto"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.parent.name == scan_saving.session
    assert parent_node.parent.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:%s" % (parent_node.parent.db_name, "toto")

    scan_saving.template = "toto"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.parent.name == scan_saving.session
    assert parent_node.parent.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:tmp:%s" % (scan_saving.session, "toto")

    scan_saving_repr = """\
Parameters (default) - 

  .base_path            = '/tmp'
  .data_filename        = 'data'
  .user_name            = '{user_name}'
  .template             = 'toto'
  .images_path_relative = True
  .images_path_template = 'scan{{scan_number}}'
  .images_prefix        = '{{img_acq_device}}_'
  .date_format          = '%Y%m%d'
  .scan_number_format   = '%04d'
  .session              = '{session}'
  .date                 = '{date}'
  .scan_name            = 'scan name'
  .scan_number          = 'scan number'
  .img_acq_device       = '<images_* only> acquisition device name'
  .writer               = 'hdf5'
  .creation_date        = '{creation_date}'
  .last_accessed        = '{last_accessed}'
""".format(
        creation_date=scan_saving.creation_date,
        date=scan_saving.date,
        last_accessed=scan_saving.last_accessed,
        session=scan_saving.session,
        user_name=scan_saving.user_name,
    )

    assert info(scan_saving) == scan_saving_repr

    scan_saving.template = "toto/{session}"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.name == scan_saving.session
    assert parent_node.parent is not None
    assert parent_node.parent.name == "toto"
    assert parent_node.parent.db_name == scan_saving.session + ":tmp:toto"
    assert parent_node.db_name == "%s:%s" % (
        parent_node.parent.db_name,
        scan_saving.session,
    )


def test_simple_continuous_scan_with_session_watcher(session, scan_saving):

    m1 = getattr(setup_globals, "m1")
    counter = getattr(setup_globals, "diode")
    scan_saving.template = "toto"
    master = SoftwarePositionTriggerMaster(m1, 0, 1, 10, time=1)
    end_pos = master._calculate_undershoot(1, end=True)
    acq_dev = SamplingCounterAcquisitionDevice(counter, count_time=0.01, npoints=10)
    chain = AcquisitionChain()
    chain.add(master, acq_dev)

    vars = {
        "new_scan_cb_called": False,
        "scan_acq_chain": None,
        "scan_children": [],
        "scan_data": [],
    }

    new_scan_args = []
    new_child_args = []
    new_data_args = []
    end_scan_args = []
    end_scan_event = gevent.event.Event()

    def end(*args):
        end_scan_event.set()
        end_scan_args.append(args)

    session_watcher = gevent.spawn(
        watch_session_scans,
        scan_saving.session,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
    )
    try:
        gevent.sleep(0.1)  # wait a bit to have session watcher greenlet started
        scan = Scan(chain, save=False)
        scan.run()
        end_scan_event.wait(2.0)
    finally:
        session_watcher.kill()

    for (scan_info,) in new_scan_args:
        assert scan_info["session_name"] == scan_saving.session
        assert scan_info["user_name"] == scan_saving.user_name
        vars["scan_acq_chain"] = scan_info["acquisition_chain"]
        vars["new_scan_cb_called"] = True

    for scan_info, data_channel in new_child_args:
        vars["scan_children"].append(data_channel.name)

    for dtype, master_name, data in new_data_args:
        assert dtype == "0d"
        assert master_name == master.name
        vars["scan_data_m1"] = data["data"]["axis:m1"]
        vars["scan_data_diode"] = data["data"]["simulation_diode_controller:diode"]

    assert vars["new_scan_cb_called"]
    assert vars["scan_acq_chain"] == {
        master.name: {
            "display_names": {"simulation_diode_controller:diode": "diode"},
            "scalars_units": {"simulation_diode_controller:diode": None},
            "scalars": ["simulation_diode_controller:diode"],
            "images": [],
            "spectra": [],
            "master": {
                "scalars": ["%s:m1" % master.name],
                "scalars_units": {"%s:m1" % master.name: None},
                "images": [],
                "spectra": [],
                "display_names": {"%s:m1" % master.name: "m1"},
            },
        }
    }
    assert numpy.allclose(vars["scan_data_m1"], master._positions, atol=1e-1)
    assert pytest.approx(m1.position, end_pos)
    assert len(end_scan_args)


def test_data_watch_callback(session, diode_acq_device_factory):
    chain = AcquisitionChain()
    acquisition_device_1 = diode_acq_device_factory.get(count_time=0.1, npoints=1)
    master = SoftwareTimerMaster(0.1, npoints=1)
    chain.add(master, acquisition_device_1)

    class TestDataWatchCallback:
        def __init__(self):
            self.SCAN_NEW = False
            self.SCAN_DATA = False
            self.SCAN_END = False

        def on_state(self, scan_state):
            # what is this for ?
            return True

        def on_scan_new(self, scan_info):
            self.SCAN_NEW = True

        def on_scan_data(self, *args):
            self.SCAN_DATA = True

        def on_scan_end(self, *args):
            self.SCAN_END = True

    cb = TestDataWatchCallback()
    s = Scan(chain, save=False, data_watch_callback=cb)
    s.run()
    assert all([cb.SCAN_NEW, cb.SCAN_DATA, cb.SCAN_END])
