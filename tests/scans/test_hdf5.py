# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import setup_globals
from bliss.common import scans
from bliss.common.axis import Axis
from bliss.common.utils import get_axes_positions_iter
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


def test_hdf5_metadata(beacon, session):

    all_motors = dict(
        [
            (name, pos)
            for name, pos, _, _ in get_axes_positions_iter(on_error="ERR")
            if pos != "ERR"
        ]
    )

    roby = beacon.get("roby")
    diode = beacon.get("diode")

    s = scans.ascan(roby, 0, 10, 10, 0.01, diode, save=True, return_scan=True)
    assert s is setup_globals.SCANS[-1]

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


def test_hdf5_file_items(beacon, session):

    roby = beacon.get("roby")
    diode = beacon.get("diode")
    simu1 = beacon.get("simu1")

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
        f"{scan_name}/measurement/diode:diode": {},
        f"{scan_name}/measurement/simu1:spectrum_det0": {},
        f"{scan_name}/measurement/timer:elapsed_time": {},
        f"{scan_name}/start_time": {},
        f"{scan_name}/title": {},
    }
    for key, val in expected_dict.items():
        assert key in scan_dict
        assert val.items() <= scan_dict[key].items()


def test_hdf5_values(beacon, session):
    roby = beacon.get("roby")
    diode = beacon.get("diode")
    s = scans.ascan(roby, 0, 10, 3, 0.01, diode, save=True, return_scan=True)
    scan_file = s.writer.filename
    data = s.get_data()["diode"]
    f = h5py.File(scan_file)
    dataset = f[s.node.name]["measurement"]["diode:diode"]
    assert list(dataset) == list(data)


def test_subscan_in_hdf5(beacon, lima_simulator, dummy_acq_master, dummy_acq_device):
    chain = AcquisitionChain()
    master1 = timer.SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    dummy1 = dummy_acq_device.get(None, "dummy1", npoints=1)
    master2 = timer.SoftwareTimerMaster(0.001, npoints=50, name="timer2")
    lima_sim = beacon.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.001)
    dummy2 = dummy_acq_device.get(None, "dummy2", npoints=1)
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
