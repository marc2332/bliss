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
from bliss.shell.standard import newproposal, newsample, newdataset


@pytest.fixture
def esrf_data_policy(session, scan_tmpdir):
    session.enable_esrf_data_policy()
    scan_saving_config = session.scan_saving.scan_saving_config
    # patch config to put data to the proper test directory
    scan_saving_config["inhouse_data_root"] = os.path.join(
        scan_tmpdir, "{beamline}", "inhouse"
    )
    scan_saving_config["visitor_data_root"] = os.path.join(scan_tmpdir, "visitor")
    yield scan_saving_config
    session.disable_esrf_data_policy()


def test_inhouse_scan_saving(session, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving_config = esrf_data_policy
    assert scan_saving.beamline == scan_saving_config["beamline"]
    assert scan_saving.proposal == f"{scan_saving.beamline}{time.strftime('%y%m')}"
    assert scan_saving.base_path == scan_saving_config["inhouse_data_root"].format(
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
    scan_saving_config = esrf_data_policy
    scan_saving.proposal = "mx415"
    assert scan_saving.base_path == scan_saving_config["visitor_data_root"]


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
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server

    session.scan_saving.sample = "toto"
    session.scan_saving.dataset = "x"

    newproposal("mx415")  # should reset sample and dataset

    assert session.scan_saving.proposal == "mx415"
    assert session.scan_saving.sample == "sample"
    assert session.scan_saving.dataset == "0001"

    session.scan_saving.get()

    assert mdexp_dev.proposal == session.scan_saving.proposal


def test_data_policy_scan_check_servers(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server
    mdmgr_dev_fqdn, mdmgr_dev = metadata_manager_tango_server

    session.scan_saving.dataset = "new"

    diode = session.env_dict["diode"]
    s = loopscan(3, 0.01, diode, save=False)

    assert mdexp_dev.proposal == session.scan_saving.proposal
    assert mdmgr_dev.datasetName == "new"
    assert str(mdmgr_dev.state()) == "RUNNING"


def test_data_policy_user_functions(session, esrf_data_policy):
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
