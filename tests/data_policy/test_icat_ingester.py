# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import itertools
import gevent


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


def test_ingester_status(session, esrf_data_policy, metaexp, metamgr):
    synctimeout = 30
    mdexp_dev_fqdn, mdexp_dev = metaexp
    mdmgr_dev_fqdn, mdmgr_dev = metamgr
    icat_proxy = session.scan_saving.icat_proxy
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
