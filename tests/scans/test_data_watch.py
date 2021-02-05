# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import gevent.event
import numpy
from bliss import setup_globals
from bliss.controllers.lima.lima_base import Lima
from bliss.scanning.toolbox import ChainBuilder
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning.acquisition.mca import McaAcquisitionSlave
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.scan import Scan
from bliss.data.scan import watch_session_scans
from bliss.scanning.chain import AcquisitionChain
from bliss.common import scans
from bliss.scanning.group import Sequence
from bliss.config.streaming import DataStreamReaderStopHandler


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

    watcher_ready_event = gevent.event.Event()

    session_watcher = gevent.spawn(
        watch_session_scans,
        scan_saving.session,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
        ready_event=watcher_ready_event,
        exclude_existing_scans=False,
    )

    try:
        assert watcher_ready_event.wait(3)
        scan = Scan(chain, save=False)
        scan.run()
        assert end_scan_event.wait(3)
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
            "scalars": ["simulation_diode_sampling_controller:diode"],
            "images": [],
            "spectra": [],
            "master": {"scalars": ["%s:m1" % master.name], "images": [], "spectra": []},
        }
    }

    assert scan_info["channels"] == {
        "simulation_diode_sampling_controller:diode": {"display_name": "diode"},
        "%s:m1" % master.name: {"display_name": "m1"},
    }

    assert numpy.allclose(vars["scan_data_m1"], master._positions, atol=1e-1)
    assert pytest.approx(m1.position) == end_pos
    assert len(end_scan_args)


def test_mca_with_watcher(session):
    m0 = session.config.get("roby")
    # Get mca
    simu = session.config.get("simu1")
    mca_device = McaAcquisitionSlave(*simu.counters, npoints=3, preset_time=0.1)
    # Create chain
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(3, m0, 0, 1), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", save=False)

    new_scan_args = []
    new_child_args = []
    new_data_args = []
    end_scan_args = []
    end_scan_event = gevent.event.Event()

    def end(*args):
        end_scan_event.set()
        end_scan_args.append(args)

    watcher_ready_event = gevent.event.Event()

    session_watcher = gevent.spawn(
        watch_session_scans,
        session.name,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
        ready_event=watcher_ready_event,
        exclude_existing_scans=False,
    )

    try:
        assert watcher_ready_event.wait(3)
        scan.run()
        assert end_scan_event.wait(3)
    finally:
        session_watcher.kill()

    assert len(new_data_args) >= 1  # At least 1 event have to be received
    assert len(new_scan_args) == 1
    assert len(end_scan_args) == 1


def test_limatake_with_watcher(session, lima_simulator):
    lima_simulator = session.config.get("lima_simulator")

    ff = lima_simulator.saving.file_format
    lima_simulator.saving.file_format = "HDF5"

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
        "prepare_once": True,
        "start_once": False,
    }

    chain = AcquisitionChain(parallel_prepare=True)
    builder = ChainBuilder([lima_simulator])

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(acq_params=lima_params)
        chain.add(node)

    scan = Scan(chain, scan_info=scan_info, name="limatake", save=False)

    lima_simulator.saving.file_format = ff

    new_scan_args = []
    new_child_args = []
    new_data_args = []
    end_scan_args = []
    end_scan_event = gevent.event.Event()

    def end(*args):
        end_scan_event.set()
        end_scan_args.append(args)

    watcher_ready_event = gevent.event.Event()

    session_watcher = gevent.spawn(
        watch_session_scans,
        session.name,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
        ready_event=watcher_ready_event,
        exclude_existing_scans=False,
    )

    try:
        assert watcher_ready_event.wait(3)
        scan.run()
        assert end_scan_event.wait(3)
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


def test_parallel_scans(default_session):
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
        end_scan_args.append(args)
        if len(end_scan_args) == 2:
            end_scan_event.set()

    session_watcher = gevent.spawn(
        watch_session_scans,
        default_session.name,
        lambda *args: new_scan_args.append(args),
        lambda *args: new_child_args.append(args),
        lambda *args: new_data_args.append(args),
        end,
        ready_event=ready_event,
        exclude_existing_scans=False,
    )

    assert ready_event.wait(3.)

    g1 = gevent.spawn(s1.run)
    g2 = gevent.spawn(s2.run)
    gs = [g1, g2]

    try:
        gevent.joinall(gs, raise_error=True)
        assert end_scan_event.wait(3.)
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

    for name, array in ascan_data[-1].items():
        assert len(array) == 26, name
    for name, array in loopscan_data[-1].items():
        assert len(array) == 20, name


def test_sequence_scans(default_session):
    diode = default_session.config.get("diode")

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
        exclude_existing_scans=False,
    )

    assert ready_event.wait(timeout=3.)
    try:
        seq = Sequence()
        with seq.sequence_context() as scan_seq:
            s1 = scans.loopscan(5, .1, diode, run=False)
            scan_seq.add(s1)
            s1.run()

    finally:
        session_watcher.kill()

    # check that end of group is not received
    # assert len(end_scan_args) ==1
    gevent.sleep(.5)
    session_watcher.get()

    # assert False


def test_stop_handler(session, scan_saving, diode_acq_device_factory):
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=1)
    master = SoftwareTimerMaster(0.1, npoints=1)
    chain.add(master, acquisition_device_1)

    watcher_ready_event = gevent.event.Event()
    end_scan_event = gevent.event.Event()

    def end(*args):
        end_scan_event.set()

    stop_handler = DataStreamReaderStopHandler()
    session_watcher = gevent.spawn(
        watch_session_scans,
        scan_saving.session,
        lambda *args: None,
        lambda *args: None,
        lambda *args: None,
        end,
        ready_event=watcher_ready_event,
        stop_handler=stop_handler,
        exclude_existing_scans=False,
    )

    try:
        assert watcher_ready_event.wait(3)
        scan = Scan(chain, save=False)
        scan.run()
        assert end_scan_event.wait(3)
    finally:
        try:
            with gevent.Timeout(seconds=3):
                stop_handler.stop()
                session_watcher.join()
        except gevent.Timeout:
            session_watcher.kill()
            assert False, "A kill is not expected here"
