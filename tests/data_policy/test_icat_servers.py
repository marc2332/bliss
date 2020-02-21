# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import itertools


def _create_state(scan_saving, mdexp_dev, mdmgr_dev, state):
    if state == "OFF":
        scan_saving._icat_ensure_notrunning()
        mdexp_dev.proposal = ""
        mdexp_dev.dataRoot = scan_saving.root_path
    elif state == "STANDBY":
        scan_saving._icat_set_proposal("blc123", scan_saving.root_path)
    elif state == "ON":
        scan_saving._icat_set_proposal("blc123", scan_saving.root_path)
        scan_saving._icat_set_sample("sample")
        scan_saving._icat_set_dataset("dataset")
    elif state == "RUNNING":
        scan_saving._icat_set_proposal("blc123", scan_saving.root_path)
        scan_saving._icat_set_sample("sample")
        scan_saving._icat_set_dataset("dataset")
        mdmgr_dev.startDataset()
    scan_saving._icat_wait_until_state(
        [state], f"Failed to set ICAT state {state} for test"
    )


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
        _create_state(scan_saving, mdexp_dev, mdmgr_dev, state)
        if proposaleq:
            scan_saving.proposal = "blc123"
        else:
            scan_saving.proposal = "blc456"
        if sampleeq:
            scan_saving.sample = "sample"
        else:
            scan_saving.sample = "othersample"
        if dataseteq:
            scan_saving.dataset = "dataset"
        else:
            scan_saving.dataset = "otherdataset"
        try:
            scan_saving.icat_sync()
        except Exception as e:
            info = {
                "proposaleq": proposaleq,
                "sampleeq": sampleeq,
                "dataseteq": dataseteq,
            }
            raise RuntimeError(str(info)) from e
