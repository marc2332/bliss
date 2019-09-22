# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import setup_globals
from bliss import global_map
from bliss.common import scans
from bliss.common.axis import Axis
from bliss.scanning.scan import Scan, ScanSaving
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
    with h5py.File(scan_file, "r") as f:
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
    assert s is scans.SCANS[-1]

    iso_start_time = datetime.datetime.fromtimestamp(
        s.scan_info["start_timestamp"]
    ).isoformat()

    with h5py.File(s.writer.filename, "r") as f:
        dataset = f[s.node.name]
        assert dataset["title"].value == "ascan roby 0 10 10 0.01"
        assert dataset["start_time"].value.startswith(iso_start_time)
        assert dataset["measurement"]
        assert dataset["instrument"]
        for name, pos in dataset["instrument/positioners"].items():
            assert all_motors.pop(name) == pos.value
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
        f"{scan_name}/measurement/simulation_diode_controller:diode": {},
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
    f = h5py.File(scan_file)
    dataset = f[s.node.name]["measurement"]["simulation_diode_controller:diode"]
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
    scan = Scan(chain, "test", scan_saving=scan_saving)
    scan.run()

    scan_file = scan.writer.filename
    f = h5py.File(scan_file)

    scan_number, scan_name = scan.node.name.split("_", maxsplit=1)
    scan_index = 1
    subscan_name = f"{scan_number}{'.%d_' % scan_index}{scan_name}"

    assert f[scan.node.name]["measurement"]["timer1:elapsed_time"]
    assert f[subscan_name]["measurement"]["timer2:elapsed_time"]
    assert f[scan.node.name]["measurement"]["dummy1:nb"]
    assert f[subscan_name]["measurement"]["dummy2:nb"]


def test_image_reference_in_hdf5(alias_session, scan_tmpdir):
    env_dict = alias_session.env_dict

    # put scan file in a tmp directory
    alias_session.scan_saving.base_path = str(scan_tmpdir)

    s = scans.ascan(env_dict["robyy"], 0, 1, 2, .1, env_dict["lima_simulator"])

    f = h5py.File(s.writer.filename)
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


def test_lima_instrument_entry(alias_session, scan_tmpdir):
    env_dict = alias_session.env_dict

    # put scan file in a tmp directory
    alias_session.scan_saving.base_path = str(scan_tmpdir)

    s = scans.ascan(env_dict["robyy"], 0, 1, 3, .1, env_dict["lima_simulator"])

    f = h5py.File(s.writer.filename)

    assert (
        "saving_frame_per_file"
        in f["1_ascan/instrument/lima_simulator/lima_parameters"]
    )
    assert "acq_mode" in f["1_ascan/instrument/lima_simulator/lima_parameters"]
    assert "height" in f["1_ascan/instrument/lima_simulator/roi_counters/r1"]


def test_scan_saving_parameters(session, lima_simulator, scan_tmpdir):
    lima_sim = session.config.get("lima_simulator")
    DEFAULT_CHAIN = session.env_dict["DEFAULT_CHAIN"]

    try:
        DEFAULT_CHAIN.set_settings(
            [
                {
                    "device": lima_sim,
                    "acquisition_settings": {
                        "saving_format": "HDF5",
                        "saving_suffix": ".h5",
                    },
                }
            ]
        )

        # put scan file in a tmp directory
        session.scan_saving.base_path = str(scan_tmpdir)

        s = scans.loopscan(1, 0.01, lima_sim)
    finally:
        DEFAULT_CHAIN.set_settings([])

    f = h5py.File(
        os.path.join(
            os.path.dirname(s.writer.filename), "scan0001", "lima_simulator_0000.h5"
        )
    )
    assert f["entry_0000"]


def test_positioners_in_scan_info(alias_session, scan_tmpdir):
    env_dict = alias_session.env_dict
    lima_simulator = env_dict["lima_simulator"]
    robyy = env_dict["robyy"]
    diode = alias_session.config.get("diode")

    # put scan file in a tmp directory
    alias_session.scan_saving.base_path = str(scan_tmpdir)

    # test that positioners are remaining in for a simple counter that does not update 'scan_info'
    s1 = scans.ascan(robyy, 0, 1, 3, .1, diode, run=False)
    assert "positioners" in s1.scan_info["instrument"]
    old_pos = s1.scan_info["instrument"]["positioners"]
    s1.run()
    assert "positioners" in s1.scan_info["instrument"]
    assert s1.scan_info["instrument"]["positioners"] == old_pos

    # test that positioners are remaining in for a counter that updates 'scan_info'
    s2 = scans.ascan(robyy, 0, 1, 3, .1, lima_simulator, run=False)
    assert "positioners" in s2.scan_info["instrument"]
    old_pos = s2.scan_info["instrument"]["positioners"]
    s2.run()
    assert "positioners" in s2.scan_info["instrument"]
    assert s2.scan_info["instrument"]["positioners"] == old_pos


def test_scan_info_cleaning(alias_session, scan_tmpdir):
    env_dict = alias_session.env_dict
    lima_simulator = env_dict["lima_simulator"]
    robyy = env_dict["robyy"]
    diode = alias_session.config.get("diode")

    # put scan file in a tmp directory
    alias_session.scan_saving.base_path = str(scan_tmpdir)

    # test that positioners are remaining in for a simple counter that does not update 'scan_info'
    s1 = scans.ascan(robyy, 0, 1, 3, .1, diode)
    assert "lima_simulator" not in s1.scan_info["instrument"]

    # test that positioners are remaining in for a counter that updates 'scan_info'
    s2 = scans.ascan(robyy, 0, 1, 3, .1, lima_simulator)
    assert "lima_simulator" in s2.scan_info["instrument"]

    # test that 'lima_simulator' does not remain in 'scan_info' for a scan that it is not involved in
    s3 = scans.ascan(robyy, 0, 1, 3, .1, diode)
    assert "lima_simulator" not in s3.scan_info["instrument"]


def test_scan_saving_without_axis_in_session(default_session, scan_tmpdir):
    # put scan file in a tmp directory
    default_session.scan_saving.base_path = str(scan_tmpdir)

    diode = default_session.config.get("diode")

    s = scans.loopscan(3, .1, diode, run=False)

    assert "positioners" in s.scan_info["instrument"]
    assert s.scan_info["instrument"]["positioners"] == {}
    s.run()
    assert "positioners" in s.scan_info["instrument"]
    assert s.scan_info["instrument"]["positioners"] == {}


def test_NXclass_of_scan_meta(session, lima_simulator, scan_tmpdir):

    # put scan file in a tmp directory
    session.scan_saving.base_path = str(scan_tmpdir)
    lima_sim = session.config.get("lima_simulator")

    s = scans.loopscan(3, .1, lima_sim)
    with h5py.File(s.writer.filename, "r") as f:
        assert f["1_loopscan/scan_meta"].attrs["NX_class"] == "NXcollection"
        assert f["1_loopscan/scan_meta/sample"].attrs["NX_class"] == "NXsample"
        assert (
            f["1_loopscan/instrument/lima_simulator"].attrs["NX_class"] == "NXdetector"
        )
        assert (
            f["1_loopscan/instrument/positioners"].attrs["NX_class"] == "NXcollection"
        )
