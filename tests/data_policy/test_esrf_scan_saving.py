# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import os
from bliss.common.standard import loopscan
from bliss.common.tango import DevFailed
from bliss.shell.standard import newproposal, newsample, newdataset


def test_inhouse_scan_saving(session, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving_config = esrf_data_policy
    assert scan_saving.beamline == scan_saving_config["beamline"]
    assert scan_saving.proposal == f"{scan_saving.beamline}{time.strftime('%y%m')}"
    assert scan_saving.base_path == scan_saving_config["inhouse_data_root"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.icat_base_path == scan_saving_config["inhouse_data_root"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    with pytest.raises(AttributeError):
        scan_saving.template = "toto"
    assert scan_saving.get_path() == os.path.join(
        scan_saving.base_path,
        scan_saving.proposal,
        scan_saving.beamline,
        scan_saving.sample,
        f"{scan_saving.sample}_{scan_saving.dataset}",
    )
    scan_saving.sample = ""
    assert scan_saving.sample == "sample"
    scan_saving.dataset = "dataset"
    with pytest.raises(AttributeError):
        scan_saving.template = ""
    assert scan_saving.get_path().endswith("dataset")


def test_visitor_scan_saving(session, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving.mount_point = "fs1"
    scan_saving_config = esrf_data_policy
    scan_saving.proposal = "mx415"
    assert scan_saving.base_path == scan_saving_config["visitor_data_root"]["fs1"]
    assert scan_saving.icat_base_path == scan_saving_config["visitor_data_root"]["fs1"]


def test_tmp_scan_saving(session, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving.mount_point = "fs1"
    scan_saving_config = esrf_data_policy
    scan_saving.proposal = "test123"
    expected = scan_saving_config["tmp_data_root"]["fs1"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.base_path == expected
    expected = scan_saving_config["icat_tmp_data_root"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.icat_base_path == expected


def test_auto_dataset_increment(session, esrf_data_policy):
    scan_saving = session.scan_saving
    assert scan_saving.dataset == "0001"
    path = scan_saving.get_path()
    os.makedirs(path)
    assert scan_saving.dataset == "0001"
    scan_saving.dataset = ""
    assert scan_saving.dataset == "0002"
    path = scan_saving.get_path()
    os.makedirs(path)
    new_filename = os.path.join(path, scan_saving.data_filename + ".h5")
    with open(new_filename, "w") as f:
        scan_saving.dataset = ""
        assert scan_saving.dataset == "0003"
    scan_saving.dataset = "dataset"
    path = scan_saving.get_path()
    os.makedirs(path)
    scan_saving.dataset = "dataset"
    assert scan_saving.dataset == "dataset_0002"
    assert scan_saving.get_path().endswith("dataset_0002")


def test_newproposal(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    scan_saving = session.scan_saving
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server

    scan_saving.sample = "toto"
    scan_saving.dataset = "x"
    newproposal("mx415")  # should reset sample and dataset
    assert scan_saving.proposal == "mx415"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    scan_saving.get()
    assert mdexp_dev.proposal == scan_saving.proposal


def test_data_policy_scan_check_servers(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    scan_saving = session.scan_saving
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server
    mdmgr_dev_fqdn, mdmgr_dev = metadata_manager_tango_server

    scan_saving.proposal = "newproposal"
    scan_saving.sample = "newsample"
    scan_saving.dataset = "newdataset"

    diode = session.env_dict["diode"]
    s = loopscan(3, 0.01, diode, save=False)

    assert mdexp_dev.proposal == "newproposal"
    assert mdexp_dev.sample == "newsample"
    assert mdmgr_dev.datasetName == "newdataset"
    assert str(mdmgr_dev.state()) == "RUNNING"
    assert session.scan_saving.root_path == mdmgr_dev.dataFolder

    session.scan_saving.proposal = "testproposal"
    s = loopscan(3, 0.01, diode, save=False)
    assert session.scan_saving.root_path != mdmgr_dev.dataFolder
    assert session.scan_saving.icat_root_path == mdmgr_dev.dataFolder


def test_data_policy_user_functions(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    scan_saving = session.scan_saving
    newproposal = session.env_dict["newproposal"]
    newsample = session.env_dict["newsample"]
    newdataset = session.env_dict["newdataset"]

    assert scan_saving.proposal == f"{scan_saving.beamline}{time.strftime('%y%m')}"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    newproposal("toto")
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    newsample("tata")
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "tata"
    assert scan_saving.dataset == "0001"
    newdataset("tutu")
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "tata"
    assert scan_saving.dataset == "tutu"
    newproposal()
    assert scan_saving.proposal == f"{scan_saving.beamline}{time.strftime('%y%m')}"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"


def test_data_policy_name_validation(session, esrf_data_policy):
    scan_saving = session.scan_saving

    for name in ("with,", "with:", "with;"):
        with pytest.raises(ValueError):
            scan_saving.proposal = name
        with pytest.raises(ValueError):
            scan_saving.sample = name
        with pytest.raises(ValueError):
            scan_saving.dataset = name

    for name in (" HG- 64", "HG__64", "hg_64", "  H -- G   -- 6_4  "):
        scan_saving.proposal = name
        assert scan_saving.proposal == "hg64"

    for name in (" sample Name", "sample  Name", "  sample -- Name "):
        scan_saving.sample = name
        assert scan_saving.sample == "sample_Name"

    for name in (" dataset Name", "dataset  Name", "  dataset -- Name "):
        scan_saving.dataset = name
        assert scan_saving.dataset == "dataset_Name"


def test_session_scan_saving_clone(
    session, esrf_data_policy, metadata_manager_tango_server
):
    scan_saving = session.scan_saving

    # just to create a tango dev proxy in scan saving
    mdm = scan_saving.metadata_manager

    # create a clone
    scan_saving2 = scan_saving.clone()

    # check that the clone is a clone
    # and that the SLOTS are the same (shallow copy)
    assert id(scan_saving) != id(scan_saving2)
    assert scan_saving2._tango_metadata_manager is not None
    assert id(scan_saving._tango_metadata_manager) == id(
        scan_saving2._tango_metadata_manager
    )

    # check that the same redis structure is used by the clone
    scan_saving.proposal = "toto"
    assert scan_saving2.proposal == "toto"


def test_mount_points(session, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving_config = esrf_data_policy

    # Test setting mount points
    for mp in ["", "fs1", "fs2", "fs3"]:
        scan_saving.mount_point = mp
        assert scan_saving.mount_point == mp
    with pytest.raises(ValueError):
        scan_saving.mount_point = "non-existing"
    scan_saving.mount_point == mp

    # Test temp mount points (has sf1 and sf2 and fixed icat)
    scan_saving.proposal = "temp123"

    icat_expected = scan_saving_config["icat_tmp_data_root"].format(
        beamline=scan_saving.beamline
    )

    scan_saving.mount_point = ""
    expected = scan_saving_config["tmp_data_root"]["fs1"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == icat_expected

    scan_saving.mount_point = "fs1"
    expected = scan_saving_config["tmp_data_root"]["fs1"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == icat_expected

    scan_saving.mount_point = "fs2"
    expected = scan_saving_config["tmp_data_root"]["fs2"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == icat_expected

    scan_saving.mount_point = "fs3"
    expected = scan_saving_config["tmp_data_root"]["fs1"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == icat_expected

    # Test visitor mount points (has sf1 and sf3 and no fixed icat)
    scan_saving.proposal = "hg123"

    scan_saving.mount_point = ""
    expected = scan_saving_config["visitor_data_root"]["fs1"]
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    scan_saving.mount_point = "fs1"
    expected = scan_saving_config["visitor_data_root"]["fs1"]
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    scan_saving.mount_point = "fs2"
    expected = scan_saving_config["visitor_data_root"]["fs1"]
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    scan_saving.mount_point = "fs3"
    expected = scan_saving_config["visitor_data_root"]["fs3"]
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    # Test inhouse mount points (no named mount points)
    scan_saving.proposal = "blc123"

    expected = scan_saving_config["inhouse_data_root"].format(
        beamline=scan_saving.beamline
    )

    scan_saving.mount_point = ""
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    scan_saving.mount_point = "fs1"
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    scan_saving.mount_point = "fs2"
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected

    scan_saving.mount_point = "fs3"
    assert scan_saving.base_path == expected
    assert scan_saving.icat_base_path == expected


def test_session_ending(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server
    mdmgr_dev_fqdn, mdmgr_dev = metadata_manager_tango_server
    scan_saving = session.scan_saving
    scan_saving.newproposal("hg123")
    scan_saving.newsample("sample1")

    scan_saving.icat_sync()
    os.makedirs(scan_saving.root_path)
    assert scan_saving.proposal == "hg123"
    assert scan_saving.sample == "sample1"
    assert scan_saving.dataset == "0001"
    scan_saving._icat_wait_until_state(["RUNNING"])
    assert mdexp_dev.proposal == "hg123"
    assert mdexp_dev.sample == "sample1"
    assert mdmgr_dev.datasetName == "0001"

    scan_saving.enddataset()
    assert scan_saving.proposal == "hg123"
    assert scan_saving.sample == "sample1"
    assert scan_saving.dataset == "0002"
    scan_saving._icat_wait_until_state(["STANDBY"])
    assert mdexp_dev.proposal == "hg123"
    assert mdexp_dev.sample == "sample1"
    assert mdmgr_dev.datasetName == ""

    scan_saving.icat_sync()
    assert scan_saving.proposal == "hg123"
    assert scan_saving.sample == "sample1"
    assert scan_saving.dataset == "0002"
    scan_saving._icat_wait_until_state(["RUNNING"])
    assert mdexp_dev.proposal == "hg123"
    assert mdexp_dev.sample == "sample1"
    assert mdmgr_dev.datasetName == "0002"

    scan_saving.endproposal()
    assert scan_saving.proposal != "hg123"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    scan_saving._icat_wait_until_state(["STANDBY"])
    assert mdexp_dev.proposal != "hg123"
    assert mdexp_dev.sample not in ["sample", "sample1"]
    with pytest.raises(DevFailed):
        mdmgr_dev.datasetName
