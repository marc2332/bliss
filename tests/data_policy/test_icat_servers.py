# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import itertools


def _create_state(scan_saving, mdexp_dev, mdmgr_dev, state):
    """Force the ICAT servers in a certain state
    """
    if state == "OFF":
        scan_saving._icat_ensure_notrunning()
        mdexp_dev.proposal = ""
        mdexp_dev.dataRoot = dataRoot = os.path.join(
            scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
        )
    elif state == "STANDBY":
        scan_saving._icat_set_proposal("blc123")
        mdexp_dev.dataRoot = dataRoot = os.path.join(
            scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
        )
    elif state == "ON":
        scan_saving._icat_set_proposal("blc123")
        scan_saving._icat_set_sample("sample")
        scan_saving._icat_set_dataset("dataset")
        mdexp_dev.dataRoot = dataRoot = os.path.join(
            scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
        )
    elif state == "RUNNING":
        scan_saving._icat_set_proposal("blc123")
        scan_saving._icat_set_sample("sample")
        scan_saving._icat_set_dataset("dataset")
        mdexp_dev.dataRoot = dataRoot = os.path.join(
            scan_saving.base_path, "blc123", "id00", "sample", "sample_dataset"
        )
        mdmgr_dev.startDataset()
    scan_saving._icat_wait_until_state(
        [state], f"Failed to set ICAT state {state} for test"
    )
    assert mdexp_dev.dataRoot == dataRoot


def test_icat_sync(
    session,
    esrf_data_policy,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
):
    mdexp_dev_fqdn, mdexp_dev = metadata_experiment_tango_server
    mdmgr_dev_fqdn, mdmgr_dev = metadata_manager_tango_server

    scan_saving = session.scan_saving
    params = [list(scan_saving.ICAT_STATUS)] + [[True, False]] * 3
    for state, proposaleq, sampleeq, dataseteq in itertools.product(*params):
        if state == "FAULT":
            continue
        info = {
            "state": state,
            "proposaleq": proposaleq,
            "sampleeq": sampleeq,
            "dataseteq": dataseteq,
        }
        _create_state(scan_saving, mdexp_dev, mdmgr_dev, state)
        if proposaleq:
            info["proposal"] = "blc123"
            scan_saving.proposal = "blc123"
        else:
            info["proposal"] = "blc456"
            scan_saving.proposal = "blc456"
        if sampleeq:
            info["sample"] = "sample"
            scan_saving.sample = "sample"
        else:
            info["sample"] = "othersample"
            scan_saving.sample = "othersample"
        if dataseteq:
            info["dataset"] = "dataset"
            scan_saving.dataset = "dataset"
        else:
            info["dataset"] = "otherdataset"
            scan_saving.dataset = "otherdataset"
        try:
            scan_saving.icat_sync()
        except Exception as e:
            raise RuntimeError(str(info)) from e
        assert scan_saving.root_path == mdmgr_dev.dataFolder, str(info)
