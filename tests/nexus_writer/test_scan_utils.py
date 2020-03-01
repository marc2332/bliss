# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import pytest
import itertools
from glob import glob
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus
from bliss.common.scans import ct
import nxw_test_utils


@pytest.mark.parametrize(
    "data_writer, save", itertools.product(["nexus", "hdf5", "null"], [True, False])
)
def test_scan_utils(data_writer, save, nexus_writer_config):
    _test_scan_utils(data_writer=data_writer, save=save, **nexus_writer_config)


@pytest.mark.parametrize(
    "data_writer, save", itertools.product(["nexus", "hdf5", "null"], [True, False])
)
def test_scan_utils_nopolicy(data_writer, save, nexus_writer_config_nopolicy):
    _test_scan_utils(data_writer=data_writer, save=save, **nexus_writer_config_nopolicy)


@pytest.mark.parametrize(
    "data_writer, save", itertools.product(["nexus", "hdf5", "null"], [True, False])
)
def test_scan_utils_base(data_writer, save, nexus_writer_config):
    _test_scan_utils(data_writer=data_writer, save=save, **nexus_writer_config)


@pytest.mark.parametrize(
    "data_writer, save", itertools.product(["nexus", "hdf5", "null"], [True, False])
)
def test_scan_utils_base_nopolicy(data_writer, save, nexus_writer_config_nopolicy):
    _test_scan_utils(data_writer=data_writer, save=save, **nexus_writer_config_nopolicy)


@nxw_test_utils.writer_stdout_on_exception
def _test_scan_utils(
    session=None,
    tmpdir=None,
    config=True,
    policy=True,
    data_writer=None,
    save=None,
    writer=None,
    **kwargs,
):
    session.scan_saving.writer = data_writer
    scan = ct(0.1, session.env_dict["diode3"], save=save)

    # Expected file names based in the policy alone (ignore save/writer settings)
    master_filenames = {}
    if policy:
        dataset_filename = tmpdir.join(
            session.name,
            "tmp",
            "testproposal",
            "id00",
            "sample",
            "sample_0001",
            "sample_0001.h5",
        )
        sample_filename = tmpdir.join(
            session.name,
            "tmp",
            "testproposal",
            "id00",
            "sample",
            "testproposal_sample.h5",
        )
        proposal_filename = tmpdir.join(
            session.name, "tmp", "testproposal", "id00", "testproposal_id00.h5"
        )
        master_filenames = {"sample": sample_filename, "proposal": proposal_filename}
        filenames = {"dataset": dataset_filename}
    else:
        dataset_filename = tmpdir.join(session.name, "a_b.h5")
        filenames = {"dataset": dataset_filename}
    filenames.update(master_filenames)

    # Check file existence based on policy/save/writer settings
    saves_files = save and data_writer != "null"
    if saves_files:
        nxw_test_utils.wait_scan_data_exists([scan], writer=writer)
    saves_masters = saves_files and data_writer == "nexus" and config
    assert dataset_filename.check(file=1) == saves_files
    for name, f in master_filenames.items():
        assert f.check(file=1) == saves_masters
    for name, f in filenames.items():
        assert f.check(file=1) == (saves_files and (name == "dataset" or saves_masters))

    # Remove unexpected files based on writer settings
    saves_files = data_writer != "null"
    saves_masters = saves_files and data_writer == "nexus" and config
    if not saves_files:
        dataset_filename = ""
        master_filenames = {}
        filenames = {}
    elif not saves_masters:
        master_filenames = {}
        filenames.pop("sample", None)
        filenames.pop("proposal", None)

    # Check file names from session (save settings are irrelevant)
    assert scan_utils.session_filename() == dataset_filename
    assert scan_utils.session_master_filenames(config=config) == master_filenames
    assert scan_utils.session_filenames(config=config) == filenames

    # Check scan uri
    if data_writer == "nexus":
        dataset_uri = str(dataset_filename) + "::/1.1"
    elif data_writer == "hdf5":
        dataset_uri = str(dataset_filename) + "::/1_ct"
    else:
        dataset_uri = str(dataset_filename)
    if dataset_uri:
        assert nexus.exists(dataset_uri) == (save and data_writer != "null")
    else:
        assert data_writer == "null"

    # Remove unexpected files based on save/writer settings
    saves_files = save and data_writer != "null"
    saves_masters = saves_files and data_writer == "nexus" and config
    if not saves_files:
        dataset_filename = ""
        dataset_uri = ""
        master_filenames = {}
        filenames = {}
    elif not saves_masters:
        master_filenames = {}
        filenames.pop("sample", None)
        filenames.pop("proposal", None)

    # Check file names from scan object
    assert scan_utils.scan_filename(scan) == dataset_filename
    assert scan_utils.scan_filename(scan.node) == dataset_filename
    assert scan_utils.scan_uri(scan) == dataset_uri
    assert scan_utils.scan_uri(scan.node) == dataset_uri
    assert scan_utils.scan_master_filenames(scan, config=config) == master_filenames
    assert scan_utils.scan_filenames(scan, config=config) == filenames
    assert (
        scan_utils.scan_master_filenames(scan.node, config=config) == master_filenames
    )
    assert scan_utils.scan_filenames(scan.node, config=config) == filenames

    # Check file names from directory
    found = set(glob(str(tmpdir.join("**", "*.h5")), recursive=True))
    expected = set(filter(None, filenames.values()))
    assert found == expected
