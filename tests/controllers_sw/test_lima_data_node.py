# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
    lima_data_view._update()

    ref_data = scan.scan_info["instrument"]["lima_simulator"]["lima_parameters"]
    lima_files = numpy.array(
        lima_data_view._get_filenames(ref_data, *range(0, scan.scan_info["npoints"]))
    )
    filesystem_files = sorted(glob.glob(ref_data["saving_directory"] + "/*"))

    return lima_files, filesystem_files


def lima_data_view_test_assets(lima_files, filesystem_files):
    for f in filesystem_files:
        assert f in lima_files[:, 0]

    for f in set(lima_files[:, 0]):
        assert f in filesystem_files


def test_LimaDataView_edf_1_frame_per_edf(beacon, lima_simulator):

    simulator = beacon.get("lima_simulator")
    scan = loopscan(5, 0.1, simulator, save=True, run=False)


def test_LimaDataView_edf_2_frames_per_edf(beacon, lima_simulator):

    simulator = beacon.get("lima_simulator")
    scan = loopscan(5, 0.1, simulator, save=True, run=False)
    sim_params = scan.acq_chain.nodes_list[1].parameters
    sim_params["saving_frame_per_file"] = 2

    lima_files, filesystem_files = lima_data_view_test_helper(scan)
    lima_data_view_test_assets(lima_files, filesystem_files)


def test_LimaDataView_edf_1_frame_per_hdf5(beacon, lima_simulator):

    simulator = beacon.get("lima_simulator")
    scan = loopscan(5, 0.1, simulator, save=True, run=False)

    sim_params = scan.acq_chain.nodes_list[1].parameters
    sim_params["saving_format"] = "HDF5"
    sim_params["saving_suffix"] = ".h5"

    lima_data_view_test_assets(*lima_data_view_test_helper(scan))


def test_LimaDataView_edf_2_frames_per_hdf5(beacon, lima_simulator):

    simulator = beacon.get("lima_simulator")
    scan = loopscan(5, 0.1, simulator, save=True, run=False)

    sim_params = scan.acq_chain.nodes_list[1].parameters
    sim_params["saving_format"] = "HDF5"
    sim_params["saving_frame_per_file"] = 2
    sim_params["saving_suffix"] = ".h5"

    lima_files, filesystem_files = lima_data_view_test_helper(scan)
    lima_data_view_test_assets(lima_files, filesystem_files)
