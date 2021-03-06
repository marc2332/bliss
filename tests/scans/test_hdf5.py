# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import global_map, current_session
from bliss.common import scans
from bliss.common.axis import Axis
from bliss.scanning.scan import Scan
from bliss.scanning.scan_saving import ScanSaving
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition import timer
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
import numpy
import h5py
import time
import datetime
import os
import h5py


def h5dict(scan_file):
    with h5py.File(scan_file, mode="r") as f:
        items = []
        f.visititems(lambda *args: items.append(args))
        return {
            name: {key: val for key, val in obj.attrs.items()} for name, obj in items
        }


def test_hdf5_metadata(session):
    all_motors = dict(
        [
            (name, pos)
            for name, pos, _, _ in global_map.get_axes_positions_iter(on_error="ERR")
            if pos != "ERR"
        ]
    )

    roby = session.config.get("roby")
    diode = session.config.get("diode")

    s = scans.ascan(roby, 0, 10, 10, 0.01, diode, save=True, return_scan=True)
    assert s is current_session.scans[-1]

    iso_start_time = datetime.datetime.fromtimestamp(
        s.scan_info["start_timestamp"]
    ).isoformat()

    with h5py.File(s.writer.filename, mode="r") as f:
        dataset = f[s.node.name]
        assert dataset["title"][()] == "ascan roby 0 10 10 0.01"
        assert dataset["start_time"][()].startswith(iso_start_time)
        assert dataset["measurement"]
        assert dataset["instrument"]
        for name, pos in dataset["instrument/positioners"].items():
            assert all_motors.pop(name) == pos[()]
        assert len(all_motors) == 0


def test_hdf5_file_items(session):
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    simu1 = session.config.get("simu1")

    s = scans.ascan(
        roby,
        0,
        5,
        5,
        0.001,
        diode,
        simu1.counters.spectrum_det0,
        save=True,
        return_scan=True,
    )

    scan_dict = h5dict(s.writer.filename)
    scan_name = s.node.name
    expected_dict = {
        f"{scan_name}": {"NX_class": "NXentry"},
        f"{scan_name}/instrument": {"NX_class": "NXinstrument"},
        f"{scan_name}/measurement": {"NX_class": "NXcollection"},
        f"{scan_name}/measurement/axis:roby": {},
        f"{scan_name}/measurement/simulation_diode_sampling_controller:diode": {},
        f"{scan_name}/measurement/simu1:spectrum_det0": {},
        f"{scan_name}/measurement/timer:elapsed_time": {},
        f"{scan_name}/start_time": {},
        f"{scan_name}/title": {},
    }
    for key, val in expected_dict.items():
        assert key in scan_dict
        assert val.items() <= scan_dict[key].items()


def test_hdf5_values(session):
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    s = scans.ascan(roby, 0, 10, 3, 0.01, diode, save=True, return_scan=True)
    scan_file = s.writer.filename
    data = s.get_data()["diode"]
    f = h5py.File(scan_file, mode="a")
    dataset = f[s.node.name]["measurement"][
        "simulation_diode_sampling_controller:diode"
    ]
    assert list(dataset) == list(data)


def test_subscan_in_hdf5(session, lima_simulator, dummy_acq_master, dummy_acq_device):
    chain = AcquisitionChain()
    master1 = timer.SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    dummy1 = dummy_acq_device.get(None, name="dummy1", npoints=1)
    master2 = timer.SoftwareTimerMaster(0.001, npoints=50, name="timer2")
    lima_sim = session.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.001)
    dummy2 = dummy_acq_device.get(None, name="dummy2", npoints=1)
    chain.add(lima_master, dummy2)
    chain.add(master2, lima_master)
    chain.add(master1, dummy1)
    master1.terminator = False

    scan_saving = ScanSaving("test")
    scan_saving.base_path = session.scan_saving.base_path
    scan = Scan(chain, "test", scan_saving=scan_saving)
    scan.run()

    scan_file = scan.writer.filename
    f = h5py.File(scan_file, mode="a")

    scan_number, scan_name = scan.node.name.split("_", maxsplit=1)
    scan_index = 1
    subscan_name = f"{scan_number}{'.%d_' % scan_index}{scan_name}"

    assert f[scan.node.name]["measurement"]["timer1:elapsed_time"]
    assert f[subscan_name]["measurement"]["timer2:elapsed_time"]
    assert f[scan.node.name]["measurement"]["dummy1:nb"]
    assert f[subscan_name]["measurement"]["dummy2:nb"]


def test_image_reference_in_hdf5(alias_session):
    env_dict = alias_session.env_dict

    s = scans.ascan(env_dict["robyy"], 0, 1, 2, .1, env_dict["lima_simulator"])

    f = h5py.File(s.writer.filename, mode="a")
    refs = numpy.array(f["1_ascan/measurement/lima_simulator:image"])

    assert numpy.array_equal(
        refs,
        numpy.array(
            [
                [
                    "lima_simulator_0000.edf",
                    "EDF",
                    "0",
                    "",
                    "scan0001/lima_simulator_0000.edf",
                ],
                [
                    "lima_simulator_0001.edf",
                    "EDF",
                    "0",
                    "",
                    "scan0001/lima_simulator_0001.edf",
                ],
                [
                    "lima_simulator_0002.edf",
                    "EDF",
                    "0",
                    "",
                    "scan0001/lima_simulator_0002.edf",
                ],
            ],
            dtype=object,
        ),
    )


def test_lima_instrument_entry(alias_session):
    env_dict = alias_session.env_dict

    s = scans.ascan(env_dict["robyy"], 0, 1, 3, .1, env_dict["lima_simulator"])

    f = h5py.File(s.writer.filename, mode="a")

    assert "lima_simulator" in f["1_ascan/instrument/chain_meta/axis/timer/"]
    assert (
        "acq_mode"
        in f["1_ascan/instrument/chain_meta/axis/timer/lima_simulator/acq_parameters"]
    )
    assert (
        "height"
        in f["1_ascan/instrument/chain_meta/axis/timer/lima_simulator/roi_counters/r1"]
    )


def test_NXclass_of_scan_meta(session, lima_simulator):
    lima_sim = session.config.get("lima_simulator")

    s = scans.loopscan(3, .1, lima_sim)
    with h5py.File(s.writer.filename, mode="r") as f:
        assert f["1_loopscan/scan_meta"].attrs["NX_class"] == "NXcollection"
        assert (
            f["1_loopscan/instrument/chain_meta/timer/lima_simulator"].attrs["NX_class"]
            == "NXcollection"
        )
        assert (
            f["1_loopscan/instrument/positioners"].attrs["NX_class"] == "NXcollection"
        )


def test_scan_info_cleaning(alias_session):
    env_dict = alias_session.env_dict
    lima_simulator = env_dict["lima_simulator"]
    robyy = env_dict["robyy"]
    diode = alias_session.config.get("diode")

    # test that positioners are remaining in for a simple counter that does not update 'scan_info'
    s1 = scans.ascan(robyy, 0, 1, 3, .1, diode)
    with h5py.File(s1.writer.filename, mode="r") as f:
        assert "axis" not in f["1_ascan/instrument/chain_meta"]

    # test that positioners are remaining in for a counter that updates 'scan_info'
    s2 = scans.ascan(robyy, 0, 1, 3, .1, lima_simulator)
    assert "positioners" in s2.scan_info
    with h5py.File(s2.writer.filename, mode="r") as f:
        assert "lima_simulator" in f["2_ascan/instrument/chain_meta/axis/timer"]

    # test that 'lima_simulator' does not remain in 'scan_info' for a scan that it is not involved in
    s3 = scans.ascan(robyy, 0, 1, 3, .1, diode)
    with h5py.File(s3.writer.filename, mode="r") as f:
        assert "axis" not in f["3_ascan/instrument/chain_meta/"]


def test_fill_meta_mechanisms(alias_session, lima_simulator):
    lima_sim = alias_session.config.get("lima_simulator")
    transf = alias_session.config.get("transfocator_simulator")

    s = scans.loopscan(3, .1, lima_sim)
    with h5py.File(s.writer.filename, mode="r") as f:
        assert "lima_simulator" in f["1_loopscan/instrument/chain_meta/timer/"]
        assert (
            "acq_mode"
            in f["1_loopscan/instrument/chain_meta/timer/lima_simulator/acq_parameters"]
        )
        assert (
            "height"
            in f[
                "1_loopscan/instrument/chain_meta/timer/lima_simulator/roi_counters/r1"
            ]
        )
        assert "transfocator_simulator" in f["1_loopscan/instrument/"]
        assert "L1" in f["1_loopscan/instrument/transfocator_simulator"]
