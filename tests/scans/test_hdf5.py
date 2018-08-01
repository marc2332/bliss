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
            for key, val in obj.attrs.iteritems():
                yield "    %s: %s" % (key, val)


def h5dump(scan_file):
    return "\n".join(_h5dump(scan_file))


ascan_dump = """{ascan}
    NX_class: NXentry
{ascan}/measurement
    NX_class: NXcollection
{ascan}/measurement/{group_name}
{ascan}/measurement/{group_name}/{group_name}:roby
{ascan}/measurement/{group_name}/timer
{ascan}/measurement/instrument
    NX_class: NXinstrument
{ascan}/measurement/timer
{ascan}/measurement/timer/diode:diode
{ascan}/measurement/timer/simu1:spectrum_det0
{ascan}/measurement/timer/timer:elapsed_time
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

    scan_file = os.path.join(s.path, "data.h5")
    with h5py.File(scan_file, "r") as f:
        dataset = f[s.name]
        assert dataset["title"].value == u"ascan roby 0 10 10 0.01"
        assert dataset["start_time"].value.startswith(iso_start_time)
        assert dataset["measurement"]
        measurement = dataset["measurement"]
        for name, pos in measurement["instrument"]["positioners"].items():
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

    scan_file = os.path.join(s.path, "data.h5")

    scan_dump = h5dump(scan_file)

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
            in_scan = l == s.name or l.startswith(s.name + "/")
        if in_scan:
            if l.startswith(s.name + "/measurement/group_"):
                group_name = l.replace(s.name + "/measurement/", "").split("/")[0]
        else:
            continue
        if "positioner" in l:
            in_positioner = True
            continue
        else:
            in_positioner = False
        assert l == ref_ascan_dump[i].format(ascan=s.name, group_name=group_name)
        i += 1

    f = h5py.File(scan_file)
    assert (
        f[f[s.name]["measurement"][group_name]["timer"].value]
        == f[s.name]["measurement"]["timer"]
    )
