# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
from bliss.common import scans


def flush_redis(scan_saving):
    parent_node = scan_saving.get_parent_node()
    connection = parent_node.connection
    keys = connection.keys(f"{parent_node.db_name}*")
    for k in keys:
        connection.delete(k)


@pytest.mark.parametrize("writer", ["hdf5", "nexus", "null"])
def test_flush_redis(writer, session, nexus_writer_service, scan_tmpdir):
    # Prepare scanning (ensure no file or Redis keys)
    detector = session.env_dict["diode"]
    scan_saving = session.scan_saving
    scan_saving.writer = writer
    scan_saving.base_path = str(scan_tmpdir)
    get_scan_entries = scan_saving.writer_object.get_scan_entries
    try:
        os.remove(scan_saving.filename)
    except FileNotFoundError:
        pass
    flush_redis(scan_saving)

    # Scan number incrementation
    s = scans.loopscan(1, 0.1, detector, save=True)
    assert s.scan_info["scan_nb"] == 1
    s = scans.loopscan(1, 0.1, detector, save=False)
    assert s.scan_info["scan_nb"] == 1
    s = scans.loopscan(1, 0.1, detector, save=True)
    assert s.scan_info["scan_nb"] == 2
    s = scans.loopscan(1, 0.1, detector, save=False)
    assert s.scan_info["scan_nb"] == 2
    if writer == "nexus":
        expected = ["1.1", "2.1"]
    elif writer == "hdf5":
        expected = ["1_loopscan", "2_loopscan"]
    else:
        expected = []
    assert get_scan_entries() == expected

    # Flush Redis
    flush_redis(scan_saving)
    if writer == "null":
        last = 0
    else:
        last = 2

    # Continue scan number incrementation
    s = scans.loopscan(1, 0.1, detector, save=True)
    assert s.scan_info["scan_nb"] == last + 1
    s = scans.loopscan(1, 0.1, detector, save=False)
    assert s.scan_info["scan_nb"] == 1
    s = scans.loopscan(1, 0.1, detector, save=True)
    assert s.scan_info["scan_nb"] == last + 2
    s = scans.loopscan(1, 0.1, detector, save=False)
    assert s.scan_info["scan_nb"] == 2
    if writer == "nexus":
        expected = ["1.1", "2.1", "3.1", "4.1"]
    elif writer == "hdf5":
        expected = ["1_loopscan", "2_loopscan", "3_loopscan", "4_loopscan"]
    else:
        expected = []
    assert get_scan_entries() == expected
