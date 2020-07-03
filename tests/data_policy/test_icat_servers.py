# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import itertools
import gevent


def _create_state(scan_saving, mdexp_dev, mdmgr_dev, state, timeout=10):
    """Force the ICAT servers in a certain state
    """
    with gevent.Timeout(timeout):
        print(f"\nCurrent state {scan_saving.icat_state}: {scan_saving.icat_status}")
        print("Ensure not RUNNING...")
        scan_saving._icat_ensure_notrunning(timeout=None)
        print(f"Current state {scan_saving.icat_state}: {scan_saving.icat_status}")
        # maximal state is now STANDBY(2): proposal and sample specified

        print(f"Creating state {state}...")
        if state == "OFF":
            scan_saving._icat_set_proposal("", timeout=None)
            dataRoot = os.path.join(
                scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
            )
            scan_saving._icat_set_dataroot(dataRoot, timeout=None)
        elif state == "STANDBY":
            scan_saving._icat_set_proposal("blc123", timeout=None)
            dataRoot = os.path.join(
                scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
            )
            scan_saving._icat_set_dataroot(dataRoot, timeout=None)
        elif state == "ON":
            scan_saving._icat_set_proposal("blc123", timeout=None)
            scan_saving._icat_set_sample("sample", timeout=None)
            scan_saving._icat_set_dataset("dataset", timeout=None)
            dataRoot = os.path.join(
                scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
            )
            scan_saving._icat_set_dataroot(dataRoot, timeout=None)
        elif state == "RUNNING":
            scan_saving._icat_set_proposal("blc123", timeout=None)
            scan_saving._icat_set_sample("sample", timeout=None)
            scan_saving._icat_set_dataset("dataset", timeout=None)
            dataRoot = os.path.join(
                scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
            )
            scan_saving._icat_set_dataroot(dataRoot, timeout=None)
            scan_saving._icat_command(mdmgr_dev, "startDataset", timeout=None)
        scan_saving._icat_wait_until_state(
            [state], f"Failed to set ICAT state {state} for test", timeout=None
        )
        assert mdexp_dev.dataRoot == dataRoot
        print(f"Created state {scan_saving.icat_state}: {scan_saving.icat_status}")


def test_icat_sync(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    synctimeout = 30
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server
    mdmgr_dev_fqdn, mdmgr_dev = metadata_manager_tango_server

    scan_saving = session.scan_saving
    params = [list(scan_saving.ICAT_STATUS)] + [[True, False]] * 3
    for state, proposaleq, sampleeq, dataseteq in itertools.product(*params):
        if state == "FAULT":
            continue
        _create_state(scan_saving, mdexp_dev, mdmgr_dev, state, timeout=synctimeout)
        if proposaleq:
            scan_saving.proposal = "blc123"
        else:
            print("Modify proposal")
            scan_saving.proposal = "blc456"
        if sampleeq:
            scan_saving.sample = "sample"
        else:
            print("Modify sample")
            scan_saving.sample = "othersample"
        if dataseteq:
            scan_saving.dataset = "dataset"
        else:
            print("Modify dataset")
            scan_saving.dataset = "otherdataset"
        # The ICAT server are in a particular initial state
        # SCAN_SAVING maybe be out of sync
        scan_saving.icat_sync(timeout=synctimeout)
        # The ICAT server should be in RUNNING state
        # SCAN_SAVING and ICAT should be in sync
        assert scan_saving.icat_state == "RUNNING"
        assert scan_saving.root_path == mdmgr_dev.dataFolder
        assert scan_saving.proposal == mdmgr_dev.proposal
        assert scan_saving.sample == mdmgr_dev.sampleName
        assert scan_saving.dataset == mdmgr_dev.datasetName
