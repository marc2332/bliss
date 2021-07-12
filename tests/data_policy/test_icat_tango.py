# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import itertools
import gevent
import pytest
import time

from bliss.common.tango import DevFailed

from . import icat_test_utils
from .test_esrf_scan_saving import create_dataset


def _dataset_path(base_path, proposal, beamline, sample, dataset):
    return os.path.join(base_path, proposal, beamline, sample, f"{sample}_{dataset}")


def _create_state(icat_proxy, base_path, beamline, state, timeout=10):
    """Force the ICAT servers in a certain state
    """
    with gevent.Timeout(timeout):
        print(f"\n\n\nCurrent state {icat_proxy.state}: {icat_proxy.status}")
        print("Ensure not RUNNING...")
        icat_proxy.ensure_notrunning(timeout=None)
        print("Clear proposal...")
        icat_proxy.set_proposal("", timeout=None)
        print(f"Current state {icat_proxy.state}: {icat_proxy.status}")
        # maximal state is now STANDBY(2): proposal and sample specified

        print(f"Creating state {state}...")
        if state == "OFF":
            path = _dataset_path(base_path, "blc123", beamline, "sample", "dataset")
            icat_proxy.set_path(path, timeout=None)
        elif state == "STANDBY":
            icat_proxy.set_proposal("blc123", timeout=None)
            path = _dataset_path(base_path, "blc123", beamline, "sample", "dataset")
            icat_proxy.set_path(path, timeout=None)
        elif state == "ON":
            icat_proxy.set_proposal("blc123", timeout=None)
            icat_proxy.set_sample("sample", timeout=None)
            path = _dataset_path(base_path, "blc123", beamline, "sample", "dataset")
            icat_proxy.set_path(path, timeout=None)
            icat_proxy.set_dataset("dataset", timeout=None)
        elif state == "RUNNING":
            icat_proxy.set_proposal("blc123", timeout=None)
            icat_proxy.set_sample("sample", timeout=None)
            path = _dataset_path(base_path, "blc123", beamline, "sample", "dataset")
            icat_proxy.set_path(path, timeout=None)
            icat_proxy.set_dataset("dataset", timeout=None)
            icat_proxy.metadata_manager.exec_command("startDataset", timeout=None)
        icat_proxy.wait_until_state([state], timeout=None)
        assert icat_proxy.path == path
        print(f"Created state {icat_proxy.state}: {icat_proxy.status}")


@pytest.mark.skip(reason="Metadata tango servers are not reliable")
def test_tango_status(
    session, metaexp_without_backend, metamgr_without_backend, esrf_data_policy
):
    synctimeout = 30
    mdexp_dev_fqdn, mdexp_dev = metaexp_without_backend
    mdmgr_dev_fqdn, mdmgr_dev = metamgr_without_backend
    icat_proxy = session.scan_saving.icat_client
    base_path = session.scan_saving.base_path
    beamline = session.scan_saving.beamline

    params = [list(icat_proxy.STATES)] + [[True, False]] * 4
    for state, proposaleq, sampleeq, dataseteq, atomic in itertools.product(*params):
        if state == "FAULT":
            continue
        _create_state(icat_proxy, base_path, beamline, state, timeout=synctimeout)
        if proposaleq:
            print("Same proposal")
            proposal = "blc123"
        else:
            print("Modify proposal")
            proposal = "blc456"
        if sampleeq:
            print("Same sample")
            sample = "sample"
        else:
            print("Modify sample")
            sample = "othersample"
        if dataseteq:
            print("Same dataset")
            dataset = "dataset"
        else:
            print("Modify dataset")
            dataset = "otherdataset"
        dataset_path = _dataset_path(base_path, proposal, beamline, sample, dataset)
        # The ICAT server is in a particular initial state
        if atomic:
            print("Storage: atomic")
            icat_proxy.store_dataset(
                proposal, sample, dataset, dataset_path, timeout=synctimeout
            )
        else:
            print("Storage: start/stop")
            icat_proxy.start_dataset(
                proposal, sample, dataset, dataset_path, timeout=synctimeout
            )
            # The ICAT server should be in RUNNING state
            assert icat_proxy.state == "RUNNING"
            assert mdmgr_dev.proposal == proposal
            assert mdmgr_dev.sampleName == sample
            assert mdmgr_dev.datasetName == dataset
            assert mdexp_dev.dataRoot == dataset_path
            # Stop the dataset (clears the dataset name)
            icat_proxy.stop_dataset(timeout=synctimeout)
        assert icat_proxy.state == "STANDBY"
        assert mdmgr_dev.proposal == proposal
        assert mdmgr_dev.sampleName == sample
        assert mdmgr_dev.datasetName == ""
        assert mdexp_dev.dataRoot == dataset_path


def test_data_policy_scan_check_servers(
    session,
    icat_subscriber,
    esrf_data_policy_tango,
    metaexp_with_backend,
    metamgr_with_backend,
):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    _, mdexp_dev = metaexp_with_backend
    _, mdmgr_dev = metamgr_with_backend
    default_proposal = f"{scan_saving.beamline}{time.strftime('%y%m')}"

    expected = {
        "proposal": default_proposal,
        "sample": None,
        "dataset": None,
        "path": None,
        "state": "STANDBY",
    }
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.proposal_name = "proposal1"
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected["proposal"] = "proposal1"
    expected["state"] = "STANDBY"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.collection_name = "sample1"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.dataset_name = "dataset1"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    create_dataset(scan_saving)
    assert_servers(mdexp_dev, mdmgr_dev, **expected)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True, tango=True
    )

    expected["path"] = session.scan_saving.icat_root_path
    scan_saving.dataset_name = "dataset2"
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected["sample"] = "sample1"
    expected["dataset"] = ""
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.dataset_name = "dataset2"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.dataset_name = "dataset3"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.collection_name = "sample2"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    create_dataset(scan_saving)
    assert_servers(mdexp_dev, mdmgr_dev, **expected)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True, tango=True
    )

    expected["sample"] = "sample2"
    expected["path"] = scan_saving.icat_root_path
    scan_saving.dataset_name = ""
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.proposal_name = "proposal2"
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected["proposal"] = "proposal2"
    expected["path"] = None
    expected["sample"] = None
    expected["dataset"] = None
    assert_servers(mdexp_dev, mdmgr_dev, **expected)


def assert_servers(
    mdexp_dev,
    mdmgr_dev,
    proposal=None,
    sample=None,
    dataset=None,
    path=None,
    state=None,
):
    if sample is None:
        if proposal:
            sample = "please enter"
        else:
            sample = ""
    if path is None:
        if proposal:
            path = "/data/visitor"
        else:
            path = "{dataRoot}"
    assert mdexp_dev.proposal == proposal
    assert mdexp_dev.sample == sample
    if dataset is None:
        with pytest.raises(DevFailed):
            mdmgr_dev.datasetName
    else:
        assert mdmgr_dev.datasetName == dataset
    assert str(mdmgr_dev.state()) == state
    assert mdmgr_dev.dataFolder == path
