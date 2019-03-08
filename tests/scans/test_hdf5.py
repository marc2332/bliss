# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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


def _h5dump(scan_file):
    # Get items
    items = []
    with h5py.File(scan_file, "r") as f:
        f.visititems(lambda *args: items.append(args))
        # Yield lines
        for name, obj in items:
            yield name
            for key, val in obj.attrs.items():
                yield "    %s: %s" % (key, val)


def h5dump(scan_file):
    return "\n".join(_h5dump(scan_file))


ascan_dump = """{ascan}
    NX_class: NXentry
{ascan}/instrument
    NX_class: NXinstrument
{ascan}/measurement
    NX_class: NXcollection
{ascan}/measurement/axis:roby
    fullname: axis:roby
    alias: None
    has_alias: False
{ascan}/measurement/diode:diode
    fullname: diode:diode
    alias: None
    has_alias: False
{ascan}/measurement/simu1:spectrum_det0
    fullname: simu1:spectrum_det0
    alias: None
    has_alias: False
{ascan}/measurement/timer:elapsed_time
    fullname: timer:elapsed_time
    alias: None
    has_alias: False
{ascan}/start_time
{ascan}/title
"""


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

    scan_dump = h5dump(s.writer.filename)

    ref_ascan_dump = ascan_dump.split("\n")

    i = 0
    in_positioner = False
    in_scan = False
    group_name = None
    for l in scan_dump.split("\n"):
        if l.startswith(" "):
            if in_positioner:
                continue
        else:
            in_scan = l == s.node.name or l.startswith(s.node.name + "/")
        if not in_scan:
            continue
        if "positioner" in l:
            in_positioner = True
            continue
        else:
            in_positioner = False

        assert l == ref_ascan_dump[i].format(ascan=s.node.name)
        i += 1


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
