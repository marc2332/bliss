# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import contextlib
import numpy
import pytest
from bliss import setup_globals
from bliss.controllers.lima.lima_base import Lima
from bliss.scanning.toolbox import ChainBuilder
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning.acquisition.mca import McaAcquisitionSlave
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.scan import Scan
from bliss.scanning.scan_info import ScanInfo
from bliss.data.scan import ScansObserver, ScansWatcher
from bliss.scanning.chain import AcquisitionChain
from bliss.common import scans
from bliss.scanning.group import Sequence


@pytest.fixture
def test_observer(mocker):
    """Helper to check post mortem the events from the scans watcher"""
    observer = mocker.Mock(spec=ScansObserver)

    def read_scan_info(observer, method_name):
        call = getattr(observer, method_name).call_args_list[0]
        scan_info = call[0][1]
        return scan_info

    def read_scalar_data(observer, channel_name, scan_db_name):
        data = []
        for call_args in observer.on_scalar_data_received.call_args_list:
            kwargs = call_args[1]
            if channel_name is not None and kwargs["channel_name"] != channel_name:
                continue
            if scan_db_name is not None and kwargs["scan_db_name"] != scan_db_name:
                continue
            data.append(kwargs["data_bunch"])
        if len(data) == 0:
            return []
        return numpy.concatenate(data)

    observer.on_scan_created__scan_info = lambda: read_scan_info(
        observer, "on_scan_created"
    )
    observer.on_scan_started__scan_info = lambda: read_scan_info(
        observer, "on_scan_started"
    )
    observer.on_scan_finished__scan_info = lambda: read_scan_info(
        observer, "on_scan_finished"
    )
    observer.on_scalar_data_received__get_data = lambda channel_name, scan_db_name: read_scalar_data(
        observer, channel_name, scan_db_name
    )

    yield observer


@contextlib.contextmanager
def watching(session, observer, exclude_groups=False):
    watcher = ScansWatcher(session.name)
    watcher.set_exclude_existing_scans(True)
    if not exclude_groups:
        watcher.set_watch_scan_group(True)
    watcher.set_observer(observer)
    session_watcher = gevent.spawn(watcher.run)
    watcher.wait_ready(timeout=3)
    try:
        yield watcher
    finally:
        gevent.sleep(0.5)
        session_watcher.kill()


def test_simple_continuous_scan_with_session_watcher(session, test_observer):

    m1 = getattr(setup_globals, "m1")
    counter = getattr(setup_globals, "diode")
    master = SoftwarePositionTriggerMaster(m1, 0, 1, 10, time=1)
    acq_dev = SamplingCounterAcquisitionSlave(counter, count_time=0.01, npoints=10)
    chain = AcquisitionChain()
    chain.add(master, acq_dev)

    with watching(session, test_observer):
        scan = Scan(chain, save=False)
        scan.run()

    test_observer.on_scan_created.assert_called_once()
    test_observer.on_scan_started.assert_called_once()
    test_observer.on_scalar_data_received.assert_called()
    test_observer.on_scan_finished.assert_called_once()

    scan_info = test_observer.on_scan_created__scan_info()
    acquisition_chain = scan_info["acquisition_chain"][master.name]
    assert len(acquisition_chain["devices"]) == 2
    assert acquisition_chain["scalars"] == [
        "simulation_diode_sampling_controller:diode"
    ]
    assert acquisition_chain["images"] == []
    assert acquisition_chain["spectra"] == []
    assert acquisition_chain["master"] == {
        "scalars": ["%s:m1" % master.name],
        "images": [],
        "spectra": [],
    }
    assert scan_info["channels"] == {
        "simulation_diode_sampling_controller:diode": {
            "display_name": "diode",
            "dim": 0,
        },
        "%s:m1" % master.name: {"display_name": "m1", "dim": 0},
    }
    scan_data_m1 = []
    for call_args in test_observer.on_scalar_data_received.call_args_list:
        kwargs = call_args[1]
        if kwargs["channel_name"] == "axis:m1":
            scan_data_m1.append(kwargs["data_bunch"])

    scan_data_m1 = numpy.concatenate(scan_data_m1)
    assert numpy.allclose(scan_data_m1, master._positions, atol=1e-1)


def test_mca_with_watcher(session, test_observer):
    m0 = session.config.get("roby")
    simu = session.config.get("simu1")
    mca_device = McaAcquisitionSlave(*simu.counters, npoints=3, preset_time=0.1)
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(3, m0, 0, 1), mca_device)
    scan = Scan(chain, "mca_test", save=False)

    with watching(session, test_observer):
        scan.run()

    test_observer.on_scan_created.assert_called_once()
    test_observer.on_scan_started.assert_called_once()
    test_observer.on_ndim_data_received.assert_called()
    test_observer.on_scan_finished.assert_called_once()

    sf = ScanInfo()
    device_key = sf._get_key_from_acq_obj(mca_device)
    scan_info = test_observer.on_scan_started__scan_info()
    assert device_key in scan_info["devices"]
    assert scan_info["devices"][device_key]["type"] == "mca"


def test_limatake_with_watcher(session, lima_simulator, test_observer):
    lima_simulator = session.config.get("lima_simulator")

    ff = lima_simulator.saving.file_format
    lima_simulator.saving.file_format = ff

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
        lima_acq_obj = node.acquisition_obj

    scan = Scan(chain, name="limatake", save=False)

    with watching(session, test_observer):
        scan.run()

    test_observer.on_scan_created.assert_called_once()
    test_observer.on_scan_started.assert_called_once()
    test_observer.on_lima_ref_received.assert_called()
    test_observer.on_scan_finished.assert_called_once()

    sf = ScanInfo()
    device_key = sf._get_key_from_acq_obj(lima_acq_obj)
    scan_info = test_observer.on_scan_started__scan_info()
    assert device_key in scan_info["devices"]
    assert scan_info["devices"][device_key]["type"] == "lima"


def test_data_watch_callback(session, diode_acq_device_factory, mocker):
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


def test_parallel_scans(default_session, test_observer):
    diode = default_session.config.get("diode")
    sim_ct_gauss = default_session.config.get("sim_ct_gauss")
    robz = default_session.config.get("robz")

    s1 = scans.loopscan(20, .1, diode, run=False)
    s2 = scans.ascan(robz, 0, 10, 25, .09, sim_ct_gauss, run=False)

    with watching(default_session, test_observer):
        g1 = gevent.spawn(s1.run)
        g2 = gevent.spawn(s2.run)
        gs = [g1, g2]
        gevent.joinall(gs, raise_error=True)

    assert len(test_observer.on_scan_created.call_args_list) == 2
    assert len(test_observer.on_scan_started.call_args_list) == 2
    assert len(test_observer.on_scan_finished.call_args_list) == 2

    scan_info_list = [c[0][1] for c in test_observer.on_scan_created.call_args_list]

    loopscan_scan_info = [si for si in scan_info_list if si["type"] == "loopscan"][0]
    loopscan_id = loopscan_scan_info["node_name"]
    ascan_scan_info = [si for si in scan_info_list if si["type"] == "ascan"][0]
    ascan_id = ascan_scan_info["node_name"]

    loopscan_data = test_observer.on_scalar_data_received__get_data(
        channel_name="simulation_diode_sampling_controller:diode",
        scan_db_name=loopscan_id,
    )

    ascan_data = test_observer.on_scalar_data_received__get_data(
        channel_name="simulation_counter_controller:sim_ct_gauss", scan_db_name=ascan_id
    )

    assert len(ascan_data) == 26
    assert len(loopscan_data) == 20


def test_scan_sequence(default_session, mocker, test_observer):
    diode = default_session.config.get("diode")

    with watching(default_session, test_observer):
        seq = Sequence()
        with seq.sequence_context() as scan_seq:
            s1 = scans.loopscan(5, .1, diode, run=False)
            scan_seq.add(s1)
            s1.run()

    assert len(test_observer.on_scan_created.call_args_list) == 2
    assert len(test_observer.on_scan_started.call_args_list) == 2
    assert len(test_observer.on_scan_finished.call_args_list) == 2


def test_scan_sequence_excluding_groups(default_session, test_observer):
    diode = default_session.config.get("diode")

    with watching(default_session, test_observer, exclude_groups=True):
        seq = Sequence()
        with seq.sequence_context() as scan_seq:
            s1 = scans.loopscan(5, .1, diode, run=False)
            scan_seq.add(s1)
            s1.run()

    test_observer.on_scan_created.assert_called_once()
    test_observer.on_scan_started.assert_called_once()
    test_observer.on_scan_finished.assert_called_once()


def test_watcher_stop(session, diode_acq_device_factory, test_observer):
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=100)
    master = SoftwareTimerMaster(0.1, npoints=1)
    chain.add(master, acquisition_device_1)

    try:
        with watching(session, test_observer) as watcher:
            scan = Scan(chain, save=False)
            g = gevent.spawn(scan.run)
            gevent.sleep(3)
            watcher.stop()

        test_observer.on_scan_created.assert_called_once()
        test_observer.on_scan_started.assert_called_once()
        test_observer.on_scan_finished.assert_not_called()
    finally:
        g.kill()


def test_scan_observer(
    session, scan_saving, diode_acq_device_factory, test_observer, mocker
):
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=1)
    master = SoftwareTimerMaster(0.1, npoints=1)
    chain.add(master, acquisition_device_1)
    scan = Scan(chain, "test", save=False)

    def side_effect(timing):
        if timing == acquisition_device_1.META_TIMING.PREPARED:
            return {"kind": "foo"}
        else:
            return None

    acquisition_device_1.get_acquisition_metadata = mocker.Mock(side_effect=side_effect)

    with watching(session, test_observer):
        scan.run()

    # TODO check the order of the received events
    test_observer.on_scan_created.assert_called_once()
    test_observer.on_scan_started.assert_called_once()
    test_observer.on_scan_finished.assert_called_once()

    # Check that the scan_info looks like what it is expected
    sf = ScanInfo()
    device_key = sf._get_key_from_acq_obj(acquisition_device_1)

    scan_info = test_observer.on_scan_created__scan_info()
    assert scan_info["session_name"] == scan_saving.session
    assert scan_info["user_name"] == scan_saving.user_name
    assert "positioners_start" in scan_info["positioners"]
    assert "start_timestamp" in scan_info
    assert device_key in scan_info["devices"]

    scan_info = test_observer.on_scan_started__scan_info()
    assert "kind" in scan_info["devices"][device_key]

    scan_info = test_observer.on_scan_finished__scan_info()
    assert "end_timestamp" in scan_info
    assert "positioners_end" in scan_info["positioners"]
