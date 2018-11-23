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
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.scanning.scan import Scan, ScanSaving
from bliss.data.scan import get_data, watch_session_scans
from bliss.scanning.chain import AcquisitionChain


@pytest.fixture
def scan_saving():
    ss = ScanSaving("test")
    prev_template = ss.template
    yield ss
    ss.template = prev_template


def test_scan_saving(beacon, scan_saving):
    scan_saving.template = "{session}/toto"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.name == scan_saving.session
    assert parent_node.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:%s" % (parent_node.parent.db_name, "toto")

    scan_saving.template = "toto"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.name == scan_saving.session
    assert parent_node.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:%s" % (scan_saving.session, "toto")

    assert (
        repr(scan_saving)
        == """\
Parameters (default)
  .base_path            = '/tmp/scans'
  .data_filename        = 'data'
  .date                 = '{date}'
  .date_format          = '%Y%m%d'
  .images_path_relative = True
  .images_path_template = 'scan{{scan_number}}'
  .images_prefix        = '{{img_acq_device}}_'
  .img_acq_device       = '<images_* only> acquisition device name'
  .scan_name            = 'scan name'
  .scan_number          = 'scan number'
  .scan_number_format   = '%04d'
  .session              = '{session}'
  .template             = 'toto'
  .user_name            = '{user_name}'
  .writer               = 'hdf5'
""".format(
            date=scan_saving.date,
            session=scan_saving.session,
            user_name=scan_saving.user_name,
        )
    )

    scan_saving.template = "toto/{session}"
    parent_node = scan_saving.get()["parent"]
    assert parent_node.name == scan_saving.session
    assert parent_node.parent is not None
    assert parent_node.parent.name == "toto"
    assert parent_node.parent.db_name == scan_saving.session + ":toto"
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
    acq_dev = SamplingCounterAcquisitionDevice(counter, 0.01, npoints=10)
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
    session_watcher = watch_session_scans(
        scan_saving.session,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        wait=False,
    )
    try:
        gevent.sleep(0.1)  # wait a bit to have session watcher greenlet started
        scan = Scan(chain, save=False)
        scan.run()
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
        assert data["master_channels"] == ["%s:m1" % master_name]
        vars["scan_data_m1"] = data["data"][data["master_channels"][0]]
        vars["scan_data_diode"] = data["data"]["diode:diode"]

    assert vars["new_scan_cb_called"]
    assert vars["scan_acq_chain"] == {
        master.name: {
            "scalars": ["diode:diode"],
            "images": [],
            "spectra": [],
            "master": {"scalars": ["%s:m1" % master.name], "images": [], "spectra": []},
        }
    }
    assert numpy.allclose(vars["scan_data_m1"], master._positions, atol=1e-1)
    assert pytest.approx(m1.position(), end_pos)
