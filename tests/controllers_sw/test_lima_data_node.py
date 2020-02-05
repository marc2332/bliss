# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
import glob
from bliss.common.scans import loopscan, DEFAULT_CHAIN


def lima_data_view_test_helper(scan):
    scan.run()

    for node in scan.node.iterator.walk(wait=False, filter="lima"):
        image_node = node

    lima_data_view = image_node.get(0)
    ref_data = image_node.info.get_all()

    lima_files = numpy.array(lima_data_view.get_filenames())

    filesystem_files = sorted(glob.glob(ref_data["saving_directory"] + "/*"))

    return lima_files, filesystem_files


def lima_data_view_test_assets(lima_files, filesystem_files):
    for f in filesystem_files:
        assert f in lima_files[:, 0]

    for f in set(lima_files[:, 0]):
        assert f in filesystem_files


def test_LimaNode_ref_data(default_session, lima_simulator, scan_tmpdir):
    scan_saving = default_session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    simulator = default_session.config.get("lima_simulator")
    scan = loopscan(5, 0.1, simulator, save=True)

    for node in scan.node.iterator.walk(wait=False, filter="lima"):
        image_node = node

    lima_data_view = image_node.get(0)
    lima_data_view._update()

    ref_data = image_node.info.get_all()

    assert "user_detector_name" in ref_data


def test_LimaDataView_edf_1_frame_per_edf(default_session, lima_simulator, scan_tmpdir):
    scan_saving = default_session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    simulator = default_session.config.get("lima_simulator")
    scan = loopscan(5, 0.1, simulator, save=True, run=False)

    lima_files, filesystem_files = lima_data_view_test_helper(scan)
    lima_data_view_test_assets(lima_files, filesystem_files)


def test_LimaDataView_edf_2_frames_per_edf(
    default_session, lima_simulator, scan_tmpdir
):
    scan_saving = default_session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    simulator = default_session.config.get("lima_simulator")

    fpf = simulator.saving.frames_per_file
    ff = simulator.saving.file_format

    simulator.saving.frames_per_file = 2
    simulator.saving.file_format = "EDF"

    scan = loopscan(5, 0.1, simulator, save=True, run=False)

    simulator.saving.frames_per_file = fpf
    simulator.saving.file_format = ff

    lima_files, filesystem_files = lima_data_view_test_helper(scan)
    lima_data_view_test_assets(lima_files, filesystem_files)


def test_LimaDataView_edf_1_frame_per_hdf5(
    default_session, lima_simulator, scan_tmpdir
):
    scan_saving = default_session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    simulator = default_session.config.get("lima_simulator")

    ff = simulator.saving.file_format
    simulator.saving.file_format = "HDF5"

    scan = loopscan(5, 0.1, simulator, save=True, run=False)

    simulator.saving.file_format = ff

    lima_data_view_test_assets(*lima_data_view_test_helper(scan))


def test_LimaDataView_edf_2_frames_per_hdf5(
    default_session, lima_simulator, scan_tmpdir
):
    scan_saving = default_session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    simulator = default_session.config.get("lima_simulator")

    fpf = simulator.saving.frames_per_file
    ff = simulator.saving.file_format

    simulator.saving.frames_per_file = 2
    simulator.saving.file_format = "HDF5"

    scan = loopscan(5, 0.1, simulator, save=True, run=False)

    simulator.saving.frames_per_file = fpf
    simulator.saving.file_format = ff

    lima_files, filesystem_files = lima_data_view_test_helper(scan)
    lima_data_view_test_assets(lima_files, filesystem_files)
