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

def test_hdf5_metadata(beacon):
    session = beacon.get("test_session")
    session.setup()
 
    all_motors = dict([(name, pos) for name, pos, _ in get_axes_positions_iter(on_error='ERR') if pos!='ERR'])
    
    roby = beacon.get("roby")
    diode = beacon.get("diode")

    s = scans.ascan(roby, 0, 10, 10, 0.01, diode, save=True, return_scan=True)
    assert s is setup_globals.SCANS[-1]

    iso_start_time = datetime.datetime.fromtimestamp(s.scan_info["start_timestamp"]).isoformat()

    scan_file = os.path.join(s.path, "data.h5")
    with h5py.File(scan_file, "r") as f:
        dataset = f[s.name]
        assert dataset.attrs["title"] == "ascan roby 0 10 10 0.01"
        assert dataset.attrs["start_time"].startswith(iso_start_time)
        assert dataset["measurement"]
        measurement = dataset["measurement"]
        for name, pos in measurement["instrument"]["positioners"].items():
            assert all_motors.pop(name) == pos.value
        assert len(all_motors) == 0
