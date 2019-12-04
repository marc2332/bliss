# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import numpy
from bliss import setup_globals
from bliss.controllers.lima.lima_base import Lima
from bliss.scanning.toolbox import ChainBuilder
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning.scan import Scan, ScanSaving
from bliss.data.scan import watch_session_scans
from bliss.scanning.chain import AcquisitionChain
from bliss.shell.standard import info
from bliss.common import scans


@pytest.fixture
def scan_saving():
    ss = ScanSaving("test")
    prev_template = ss.template
    yield ss
    ss.template = prev_template


def test_scan_saving(session, scan_saving):
    scan_saving.base_path = "/tmp"
    scan_saving.template = "{session}/toto"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.name == "toto"
    assert parent_node.parent is not None
    assert parent_node.parent.parent.name == scan_saving.session
    assert parent_node.parent.parent.db_name == scan_saving.session
    assert parent_node.db_name == "%s:%s" % (parent_node.parent.db_name, "toto")

    scan_saving.template = "toto"
    parent_node = scan_saving.get_parent_node()
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
--------------  ---------  -----------------
does not exist  filename   /tmp/toto/data.h5
does not exist  root_path  /tmp/toto
--------------  ---------  -----------------""".format(
        creation_date=scan_saving.creation_date,
        date=scan_saving.date,
        last_accessed=scan_saving.last_accessed,
        session=scan_saving.session,
        user_name=scan_saving.user_name,
    )

    assert info(scan_saving) == scan_saving_repr

    scan_saving.template = "toto/{session}"
    parent_node = scan_saving.get_parent_node()
    assert parent_node.name == scan_saving.session
    assert parent_node.parent is not None
    assert parent_node.parent.name == "toto"
    assert parent_node.parent.db_name == scan_saving.session + ":tmp:toto"
    assert parent_node.db_name == "%s:%s" % (
        parent_node.parent.db_name,
        scan_saving.session,
    )

    no_saving_info_tail = """\
  .last_accessed        = '{last_accessed}'
---------
NO SAVING
---------""".format(
        last_accessed=scan_saving.last_accessed
    )

    scan_saving.writer = "null"  # set no saving
    assert info(scan_saving).endswith(no_saving_info_tail)


def test_simple_continuous_scan_with_session_watcher(session, scan_saving):

    m1 = getattr(setup_globals, "m1")
    counter = getattr(setup_globals, "diode")
    scan_saving.template = "toto"
    master = SoftwarePositionTriggerMaster(m1, 0, 1, 10, time=1)
    end_pos = master._calculate_undershoot(1, end=True)
    acq_dev = SamplingCounterAcquisitionSlave(counter, count_time=0.01, npoints=10)
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
        vars["scan_data_diode"] = data["data"][
            "simulation_diode_sampling_controller:diode"
        ]

    assert vars["new_scan_cb_called"]
    assert vars["scan_acq_chain"] == {
        master.name: {
            "display_names": {"simulation_diode_sampling_controller:diode": "diode"},
            "scalars_units": {"simulation_diode_sampling_controller:diode": None},
            "scalars": ["simulation_diode_sampling_controller:diode"],
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


def test_limatake_with_watcher(session, lima_simulator):
    lima_simulator = session.config.get("lima_simulator")

    scan_info = {
        "npoints": 1,
        "count_time": 0.01,
        "type": "loopscan",
        "save": False,
        "title": "limatake",
        "sleep_time": None,
        "start": [],
        "stop": [],
        "saving_statistics_history": 1,
    }

    lima_params = {
        "acq_nb_frames": 1,
        "acq_expo_time": 0.01,
        "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER",
        "saving_format": "HDF5",
        "saving_suffix": ".h5",
        "prepare_once": True,
        "start_once": False,
    }

    chain = AcquisitionChain(parallel_prepare=True)
    builder = ChainBuilder([lima_simulator])

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(acq_params=lima_params)
        chain.add(node)

    scan = Scan(chain, scan_info=scan_info, name="limatake", save=False)

    # print(scan.acq_chain._tree)

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
        session.name,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
    )

    try:
        gevent.sleep(0.1)  # wait a bit to have session watcher greenlet started

        scan.run()

        end_scan_event.wait(2.0)
    finally:
        session_watcher.kill()

    assert len(new_data_args) >= 1  # At least 1 event have to be received
    assert len(new_scan_args) == 1
    assert len(end_scan_args) == 1


def test_data_watch_callback(session, diode_acq_device_factory):
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=1)
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

        def on_scan_new(self, *args):
            self.SCAN_NEW = True

        def on_scan_data(self, *args):
            self.SCAN_DATA = True

        def on_scan_end(self, *args):
            self.SCAN_END = True

    cb = TestDataWatchCallback()
    s = Scan(chain, save=False, data_watch_callback=cb)
    s.run()
    assert all([cb.SCAN_NEW, cb.SCAN_DATA, cb.SCAN_END])


def test_parallel_scans(default_session, scan_tmpdir):
    default_session.scan_saving.base_path = str(scan_tmpdir)

    diode = default_session.config.get("diode")
    sim_ct_gauss = default_session.config.get("sim_ct_gauss")
    robz = default_session.config.get("robz")

    s1 = scans.loopscan(20, .1, diode, run=False)
    s2 = scans.ascan(robz, 0, 10, 25, .09, sim_ct_gauss, run=False)

    new_scan_args = []
    new_child_args = []
    new_data_args = []
    end_scan_args = []
    end_scan_event = gevent.event.Event()
    ready_event = gevent.event.Event()

    def end(*args):
        end_scan_event.set()
        end_scan_args.append(args)

    session_watcher = gevent.spawn(
        watch_session_scans,
        default_session.name,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
        ready_event=ready_event,
    )

    ready_event.wait(timeout=3.)

    g1 = gevent.spawn(s1.run)
    g2 = gevent.spawn(s2.run)
    gs = [g1, g2]

    try:
        gevent.joinall(gs, raise_error=True)
        end_scan_event.wait(2.0)
    finally:
        session_watcher.kill()

    assert len(new_data_args) > 0

    loopscan_data = [
        i[2]["data"] for i in new_data_args if i[2]["scan_info"]["type"] == "loopscan"
    ]
    ascan_data = [
        i[2]["data"] for i in new_data_args if i[2]["scan_info"]["type"] == "ascan"
    ]

    expected_keys = [
        "timer:epoch",
        "timer:elapsed_time",
        "axis:robz",
        "simulation_counter_controller:sim_ct_gauss",
    ]
    assert ascan_data[-1].keys() == set(expected_keys)

    expected_keys = [
        "timer:epoch",
        "timer:elapsed_time",
        "simulation_diode_sampling_controller:diode",
    ]
    assert loopscan_data[-1].keys() == set(expected_keys)

    for array in ascan_data[-1].values():
        assert len(array) == 26
    for array in loopscan_data[-1].values():
        assert len(array) == 20
