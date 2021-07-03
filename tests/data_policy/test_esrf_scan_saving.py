# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import os
import itertools
import numpy
from bliss.common.standard import loopscan, mv
from bliss.common.utils import rounder
from bliss.common.tango import DevFailed
from bliss.common.session import set_current_session
from bliss.scanning.scan_saving import ESRFDataPolicyEvent, ScanSaving
from bliss.config import channels
from bliss.shell.standard import (
    newproposal,
    newsample,
    newcollection,
    newdataset,
    enddataset,
    endproposal,
    elog_print,
)
from bliss.common import logtools
from bliss.data.node import get_node
from bliss.icat.definitions import Definitions
from bliss.scanning.scan import Scan
from bliss.icat.dataset import Dataset
from bliss.icat.nexus import IcatToNexus, nxcharUnicode
from ..conftest import deep_compare
from . import icat_test_utils


def test_stomp(icat_publisher, icat_subscriber):
    icat_publisher.sendall(b"MYMESSAGE1\nMYMESSAGE2\n")
    assert icat_subscriber.get(timeout=5) == "MYMESSAGE1"
    assert icat_subscriber.get(timeout=5) == "MYMESSAGE2"


def test_jolokia_server(jolokia_server):
    # TODO: send test request
    pass


def test_icat_logbook_server(icat_logbook_subscriber):
    # TODO: send test request
    pass


def test_icat_backends(
    session, icat_subscriber, icat_logbook_subscriber, esrf_data_policy
):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    scan_saving.writer = "hdf5"

    diode = session.config.get("diode")
    newproposal("totoproposal")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "Proposal set to", category="info"
    )
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    newdataset()
    loopscan(1, .1, diode)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "Dataset set to", category="info"
    )
    expected = icat_test_utils.expected_icat_mq_message(scan_saving, dataset=True)
    enddataset()
    icat_test_utils.assert_icat_received(icat_subscriber, expected)


def test_inhouse_scan_saving(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving_config = esrf_data_policy
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    for bset in [False, True]:
        if bset:
            scan_saving.proposal_name = "blc123"
            icat_test_utils.assert_icat_received_current_proposal(
                scan_saving, icat_subscriber
            )
        assert scan_saving.beamline == scan_saving_config["beamline"]
        if bset:
            assert scan_saving.proposal_name == "blc123"
        else:
            assert (
                scan_saving.proposal_name
                == f"{scan_saving.beamline}{time.strftime('%y%m')}"
            )
        assert scan_saving.base_path == scan_saving_config["inhouse_data_root"].format(
            beamline=scan_saving.beamline
        )
        assert scan_saving.icat_base_path == scan_saving_config[
            "inhouse_data_root"
        ].format(beamline=scan_saving.beamline)
        assert_default_sample_dataset(scan_saving)


def test_visitor_scan_saving(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    scan_saving.mount_point = "fs1"
    scan_saving_config = esrf_data_policy
    p = scan_saving.icat_proxy.metadata_manager.proxy
    scan_saving.proposal_name = "mx415"
    assert scan_saving.base_path == scan_saving_config["visitor_data_root"]["fs1"]
    assert scan_saving.icat_base_path == scan_saving_config["visitor_data_root"]["fs1"]
    assert_default_sample_dataset(scan_saving)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)


def test_tmp_scan_saving(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    scan_saving.mount_point = "fs1"
    scan_saving_config = esrf_data_policy
    scan_saving.proposal_name = "test123"
    expected = scan_saving_config["tmp_data_root"]["fs1"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.base_path == expected
    expected = scan_saving_config["icat_tmp_data_root"].format(
        beamline=scan_saving.beamline
    )
    assert scan_saving.icat_base_path == expected
    assert_default_sample_dataset(scan_saving)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)


def assert_default_sample_dataset(scan_saving):
    assert scan_saving.collection_name == "sample"


def test_auto_dataset_increment(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    assert scan_saving.dataset_name == "0001"
    with pytest.raises(AttributeError):
        scan_saving.template = "toto"
    assert scan_saving.get_path() == os.path.join(
        scan_saving.base_path,
        scan_saving.proposal_name,
        scan_saving.beamline,
        scan_saving.collection_name,
        f"{scan_saving.collection_name}_{scan_saving.dataset_name}",
    )
    scan_saving.collection_name = ""
    assert scan_saving.collection_name == "sample"
    scan_saving.dataset_name = ""
    assert scan_saving.dataset_name == "0001"
    with pytest.raises(AttributeError):
        scan_saving.template = ""
    assert scan_saving.get_path().endswith("0001")


def create_dataset(scan_saving):
    """Create the dataset on disk and in Bliss without having to run a scan
    """
    paths = [scan_saving.root_path, scan_saving.icat_root_path]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)
    assert scan_saving.dataset is not None


def test_auto_dataset_increment(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.dataset_name == "0001"

    create_dataset(scan_saving)
    scan_saving.dataset_name = ""
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.dataset_name == "0002"

    create_dataset(scan_saving)
    path = scan_saving.get_path()
    new_filename = os.path.join(path, scan_saving.data_filename + ".h5")
    with open(new_filename, "w") as f:
        scan_saving.dataset_name = ""
        icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
        expected_dataset = icat_test_utils.expected_icat_mq_message(
            scan_saving, dataset=True
        )
        assert scan_saving.dataset_name == "0003"
        # create_dataset(scan_saving)

    scan_saving.dataset_name = "dataset"
    # No directory -> not in ICAT
    # icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )

    create_dataset(scan_saving)
    scan_saving.dataset_name = "dataset"
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    assert scan_saving.dataset_name == "dataset_0002"
    assert scan_saving.get_path().endswith("dataset_0002")


@pytest.mark.parametrize(
    "user_action,same_sample",
    [[newdataset, True], [newsample, True], [newproposal, False], [newproposal, True]],
)
def test_close_dataset(
    session, icat_subscriber, esrf_data_policy, user_action, same_sample
):
    scan_saving = session.scan_saving
    scan_saving.writer = "hdf5"
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    newproposal("myproposal")
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    if same_sample:
        newsample("mysample")

    diode = session.config.get("diode")
    loopscan(1, 0.1, diode)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    user_action(None)
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)


def test_data_policy_scan_check_servers(
    session,
    icat_subscriber,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    mdexp_dev_fqdn, mdexp_dev = metaexp_with_backend
    mdmgr_dev_fqdn, mdmgr_dev = metamgr_with_backend
    diode = session.env_dict["diode"]
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
        scan_saving, dataset=True
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
        scan_saving, dataset=True
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


def test_data_policy_objects(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    # Prepare for scanning without the Nexus writer
    diode = session.env_dict["diode"]
    scan_saving.writer = "hdf5"

    proposal = scan_saving.proposal
    collection = scan_saving.collection
    dataset = scan_saving.dataset

    assert proposal.node.type == "proposal"
    assert str(proposal) == scan_saving.proposal_name
    assert proposal.name == scan_saving.proposal_name
    assert proposal.has_samples
    assert len(list(proposal.sample_nodes)) == 1

    assert collection.node.type == "dataset_collection"
    assert str(collection) == scan_saving.collection_name
    assert collection.proposal.name == scan_saving.proposal_name
    assert collection.name == scan_saving.collection_name
    assert collection.has_datasets
    assert len(list(collection.dataset_nodes)) == 1
    assert collection.proposal.node.db_name == proposal.node.db_name

    assert dataset.node.type == "dataset"
    assert str(dataset) == scan_saving.dataset_name
    assert dataset.proposal.name == scan_saving.proposal_name
    assert dataset.collection.name == scan_saving.collection_name
    assert dataset.name == scan_saving.dataset_name
    assert not dataset.has_scans
    assert len(list(dataset.scan_nodes)) == 0
    assert dataset.proposal.node.db_name == proposal.node.db_name
    assert dataset.collection.node.db_name == collection.node.db_name

    loopscan(3, 0.01, diode)

    assert dataset.has_scans
    assert len(list(dataset.scan_nodes)) == 1

    assert dataset.path.startswith(proposal.path)
    assert dataset.path.startswith(collection.path)
    assert collection.path.startswith(proposal.path)
    assert len(dataset.path) > len(proposal.path)
    assert len(dataset.path) > len(collection.path)
    assert len(collection.path) > len(proposal.path)


def test_dataset_object(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    # Prepare for scanning without the Nexus writer
    diode = session.env_dict["diode"]
    scan_saving.writer = "hdf5"

    # First dataset
    s = loopscan(3, 0.01, diode)

    dataset = scan_saving.dataset
    assert dataset.has_scans
    assert dataset.has_data
    assert [s.name for s in dataset.scan_nodes] == [s.node.name]
    assert not dataset.is_closed

    # Second dataset
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    scan_saving.dataset_name = None
    assert dataset.is_closed
    assert scan_saving._dataset_object is None
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)

    s = loopscan(3, 0.01, diode)
    assert scan_saving.dataset.node.db_name != dataset.node.db_name

    # Third dataset
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    scan_saving.dataset_name = None
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)

    # Third dataset not in Redis yet
    n = get_node(session.name)
    walk_res = [d for d in n.walk(wait=False, include_filter="dataset")]
    assert len(walk_res) == 2

    s = loopscan(3, 0.01, diode, save=False)

    # Third dataset in Redis
    n = get_node(session.name)
    walk_res = [d for d in n.walk(wait=False, include_filter="dataset")]
    assert len(walk_res) == 3

    # Third dataset object does not exist yet
    assert scan_saving._dataset_object is None

    # Third dataset created upon using it
    dataset = scan_saving.dataset
    assert not dataset.is_closed
    assert dataset.has_scans
    assert not dataset.has_data
    assert [s.name for s in dataset.scan_nodes] == [s.node.name]

    # Does not go to a new dataset (because the current one has no data)
    scan_saving.dataset_name = None

    # Still in third dataset
    assert scan_saving.dataset.node.db_name == dataset.node.db_name
    assert not dataset.is_closed
    assert dataset.has_scans
    assert not dataset.has_data
    assert [s.name for s in dataset.scan_nodes] == [s.node.name]

    # Test walk on datasets
    n = get_node(session.name)
    walk_res = [d for d in n.walk(wait=False, include_filter="dataset")]
    assert len(walk_res) == 3


def test_icat_metadata(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    # Prepare for scanning without the Nexus writer
    scan_saving.writer = "hdf5"
    diode = session.env_dict["diode"]
    att1 = session.env_dict["att1"]
    att1.Al200()

    s = loopscan(3, 0.01, diode)
    icatfields1 = {
        "InstrumentVariables_name": "roby robz ",
        "InstrumentVariables_value": "0.0 0.0 ",
        "InstrumentSlitPrimary_vertical_offset": "0.0",
        "InstrumentSlitPrimary_horizontal_offset": "0.0",
        "InstrumentSlitPrimary_horizontal_gap": "0.0",
        "InstrumentSlitPrimary_vertical_gap": "0.0",
        "InstrumentAttenuator01_status": "in",
        "InstrumentAttenuator01_thickness": "200",
        "InstrumentAttenuator01Positioners_value": "2.5",
        "InstrumentAttenuator01Positioners_name": "att1z",
        "InstrumentAttenuator01_type": "Al",
        "InstrumentInsertionDevice_gap_value": "0.0 0.0",
        "InstrumentInsertionDevice_gap_name": "roby robz",
        "SamplePositioners_name": "roby",
        "SamplePositioners_value": "0.0",
        "Sample_name": "sample",
    }
    # Check metadata gathering
    icatfields2 = dict(scan_saving.dataset.get_current_icat_metadata())
    icatfields2.pop("startDate")
    # no endDate because dataset is not closed yet
    assert icatfields1 == icatfields2

    scan_saving.dataset_name = None

    # test reception of metadata on icat server side
    phrase = "<tns:name>SamplePositioners_name</tns:name><tns:value>roby</tns:value>"
    icat_test_utils.assert_icat_metadata_received(icat_subscriber, phrase)

    s = loopscan(3, 0.01, diode)
    # Check metadata gathering
    icatfields2 = dict(scan_saving.dataset.get_current_icat_metadata())
    icatfields2.pop("startDate")
    assert icatfields1 == icatfields2

    # Check metadata after dataset closing
    dataset = scan_saving.dataset
    scan_saving.enddataset()
    icatfields2 = dict(dataset.get_current_icat_metadata())
    icatfields2.pop("startDate")
    icatfields2.pop("endDate")
    assert icatfields1 == icatfields2

    # test walk on datasets
    n = get_node(session.name)
    walk_res = [d.name for d in n.walk(wait=False, include_filter="dataset")]
    assert len(walk_res) == 2, walk_res


def test_icat_metadata_custom(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    # Prepare for scanning without the Nexus writer
    diode = session.env_dict["diode"]
    scan_saving.writer = "hdf5"

    # do a scan in the 'normal' dataset
    loopscan(2, .1, diode)

    # create custom dataset
    scan_saving = ScanSaving("my_custom_scansaving")
    scan_saving.writer = "hdf5"
    ds_name = session.scan_saving.dataset_name
    ds_name += "_b"
    scan_saving.dataset_name = ds_name

    # scan in custom dataset with custom metadata fields
    # set before and after the scan
    definitions = Definitions()
    scan_saving.dataset.add_technique(definitions.techniques.FLUO)
    ls = loopscan(3, .1, diode, run=False)
    s = Scan(ls.acq_chain, scan_saving=scan_saving)
    scan_saving.dataset.write_metadata_field("FLUO_i0", str(17.1))
    s.run()
    scan_saving.dataset["FLUO_it"] = str(18.2)

    # close the custom dataset
    scan_saving.enddataset()

    # do another scan in the 'normal' dataset
    loopscan(3, .1, diode)

    # close the 'normal' dataset
    session.scan_saving.enddataset()

    # see if things in redis are correct
    n = get_node(session.name)
    datasets = {Dataset(d) for d in n.walk(wait=False, include_filter="dataset")}
    assert all(d.is_closed for d in datasets)
    datasets = {d.name: d for d in datasets}
    assert datasets.keys() == {"0001", "0001_b"}

    metadata_0001 = datasets["0001"].get_current_icat_metadata()
    assert len(metadata_0001) == 13, metadata_0001.keys()
    metadata_0001b = datasets["0001_b"].get_current_icat_metadata()
    assert len(metadata_0001b) == 16, metadata_0001b.keys()

    assert "startDate" in metadata_0001
    assert "startDate" in metadata_0001b
    assert "endDate" in metadata_0001
    assert "endDate" in metadata_0001b
    assert "FLUO_i0" in metadata_0001b
    assert metadata_0001["Sample_name"] == metadata_0001b["Sample_name"]
    assert metadata_0001b["definition"] == "FLUO"

    # test reception of metadata on icat server side
    phrases = ["<tns:name>0001_b</tns:name>", "<tns:name>FLUO_i0</tns:name>"]
    icat_test_utils.assert_icat_metadata_received(icat_subscriber, phrases)
    phrase = "<tns:name>0001</tns:name>"
    icat_test_utils.assert_icat_metadata_received(icat_subscriber, phrase)


def test_icat_metadata_to_nexus(session, esrf_data_policy):
    dataset = session.scan_saving.dataset
    dataset.add_technique("FLUO")
    dataset["FLUO_i0"] = "1"
    dataset.gather_metadata()
    metadict = dataset.get_current_icat_metadata()

    converter = IcatToNexus()
    nxtreedict = converter.create_nxtreedict(metadict)
    expected = {
        "FLUO": {"@NX_class": "NXsubentry", "i0": 1.0, "i0@units": ""},
        "instrument": {
            "@NX_class": "NXinstrument",
            "variables": {
                "@NX_class": "NXcollection",
                "name": numpy.array("roby robz ", dtype=nxcharUnicode),
                "value": numpy.array("0.0 0.0 ", dtype=nxcharUnicode),
            },
            "insertion_device": {
                "@NX_class": "NXinsertion_device",
                "gap": {
                    "@NX_class": "NXpositioner",
                    "name": numpy.array("roby robz", dtype=nxcharUnicode),
                    "value": numpy.array("0.0 0.0", dtype=nxcharUnicode),
                },
            },
            "primary_slit": {
                "@NX_class": "NXslit",
                "horizontal_gap": numpy.array("0.0", dtype=nxcharUnicode),
                "horizontal_offset": numpy.array("0.0", dtype=nxcharUnicode),
                "vertical_gap": numpy.array("0.0", dtype=nxcharUnicode),
                "vertical_offset": numpy.array("0.0", dtype=nxcharUnicode),
            },
        },
        "sample": {
            "@NX_class": "NXsample",
            "name": numpy.array("sample", dtype=nxcharUnicode),
            "positioners": {
                "@NX_class": "NXpositioner",
                "name": numpy.array("roby", dtype=nxcharUnicode),
                "value": numpy.array("0.0", dtype=nxcharUnicode),
            },
        },
        "start_time": nxtreedict["start_time"],
    }
    deep_compare(nxtreedict, expected)


def test_icat_metadata_namespaces(session, icat_subscriber, esrf_data_policy):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    # Prepare for scanning without the Nexus writer
    diode = session.env_dict["diode"]
    scan_saving.writer = "hdf5"

    scan_saving.newdataset("toto")

    existing = {x for x in dir(scan_saving.dataset.existing) if not x.startswith("_")}
    assert scan_saving.dataset.get_current_icat_metadata_fields() == existing

    definitions = Definitions()
    scan_saving.dataset.add_technique(definitions.techniques.FLUO)

    actual = {x for x in dir(scan_saving.dataset.expected) if not x.startswith("_")}
    expected = definitions.techniques.FLUO.fields | {
        "Sample_name",
        "Sample_description",
    }
    assert actual == expected

    # check that the expected keys do not move into existing
    existing = {x for x in dir(scan_saving.dataset.existing) if not x.startswith("_")}
    assert scan_saving.dataset.get_current_icat_metadata_fields() == existing

    loopscan(1, .1, diode)
    scan_saving.newdataset("toto1")

    # create a new dataset and see that the old technique is gone
    scan_saving.dataset.add_technique(definitions.techniques.EM)
    actual = {x for x in dir(scan_saving.dataset.expected) if not x.startswith("_")}
    expected = definitions.techniques.EM.fields | {"Sample_name", "Sample_description"}
    assert actual == expected

    # add a key through .expected and see if it pops up in existing
    scan_saving.dataset.expected.EM_images_count = "24"
    assert "EM_images_count" in dir(scan_saving.dataset.existing)
    assert scan_saving.dataset.existing.EM_images_count == "24"

    # see if setting a value to None removes it from existing
    scan_saving.dataset.existing.EM_images_count = None
    assert "EM_images_count" not in dir(scan_saving.dataset.existing)


def test_icat_metadata_inheritance(session, esrf_data_policy):
    scan_saving = session.scan_saving
    assert "Sample_name" in scan_saving.dataset.expected_fields
    assert "Sample_name" in scan_saving.dataset.existing_fields
    assert "Sample_description" in scan_saving.dataset.expected_fields
    assert "Sample_description" not in scan_saving.dataset.existing_fields
    assert scan_saving.collection.expected_fields.issubset(
        scan_saving.dataset.expected_fields
    )
    assert scan_saving.collection.existing_fields.issubset(
        scan_saving.dataset.existing_fields
    )
    assert scan_saving.collection["Sample_name"] == scan_saving.collection_name
    assert scan_saving.dataset["Sample_name"] == scan_saving.collection_name

    scan_saving.dataset["Sample_name"] += "_suffix"
    assert scan_saving.collection["Sample_name"] == scan_saving.collection_name
    assert scan_saving.dataset["Sample_name"] == scan_saving.collection_name + "_suffix"
    assert scan_saving.collection.sample_description is None
    assert scan_saving.dataset.description is None
    assert not scan_saving.collection.metadata_is_complete
    assert not scan_saving.dataset.metadata_is_complete

    scan_saving.collection.sample_description = "sample description"
    assert scan_saving.collection.sample_description == "sample description"
    assert scan_saving.dataset.description == "sample description"
    assert scan_saving.collection.metadata_is_complete
    assert scan_saving.dataset.metadata_is_complete

    scan_saving.dataset.description = "dataset description"
    assert scan_saving.collection.sample_description == "sample description"
    assert scan_saving.dataset.description == "sample description (dataset description)"
    assert scan_saving.collection.metadata_is_complete
    assert scan_saving.dataset.metadata_is_complete

    create_dataset(scan_saving)
    scan_saving.newdataset(None)

    assert scan_saving.collection["Sample_name"] == scan_saving.collection_name
    assert scan_saving.dataset["Sample_name"] == scan_saving.collection_name
    assert scan_saving.collection.sample_description == "sample description"
    assert scan_saving.dataset.description == "sample description"
    assert scan_saving.collection.metadata_is_complete
    assert scan_saving.dataset.metadata_is_complete

    scan_saving.newcollection("toto")

    assert scan_saving.collection["Sample_name"] == "toto"
    assert scan_saving.dataset["Sample_name"] == "toto"
    assert scan_saving.collection.sample_description is None
    assert scan_saving.dataset.description is None
    assert not scan_saving.collection.metadata_is_complete
    assert not scan_saving.dataset.metadata_is_complete

    scan_saving.dataset.description = "dataset description"
    assert scan_saving.collection.sample_description is None
    assert scan_saving.dataset.description == "dataset description"
    assert not scan_saving.collection.metadata_is_complete
    assert scan_saving.dataset.metadata_is_complete

    scan_saving.collection.sample_description = "sample description"
    assert scan_saving.collection.sample_description == "sample description"
    assert scan_saving.dataset.description == "dataset description"
    assert scan_saving.collection.metadata_is_complete
    assert scan_saving.dataset.metadata_is_complete

    scan_saving.dataset.description = "dataset description"
    assert scan_saving.collection.sample_description == "sample description"
    assert scan_saving.dataset.description == "sample description (dataset description)"
    assert scan_saving.collection.metadata_is_complete
    assert scan_saving.dataset.metadata_is_complete


def test_icat_metadata_freezing(session, esrf_data_policy):
    scan_saving = session.scan_saving

    mdatafield = "Sample_name"
    scan_saving.collection[mdatafield] = "value1"
    assert scan_saving.dataset[mdatafield] == "value1"
    scan_saving.collection[mdatafield] = "value2"
    assert scan_saving.dataset[mdatafield] == "value2"
    scan_saving.dataset.freeze_inherited_icat_metadata()
    scan_saving.collection[mdatafield] = "value3"
    assert scan_saving.dataset[mdatafield] == "value2"
    scan_saving.dataset.unfreeze_inherited_icat_metadata()
    assert scan_saving.dataset[mdatafield] == "value2"
    scan_saving.dataset[mdatafield] = None
    assert scan_saving.dataset[mdatafield] == "value3"


def test_data_policy_user_functions(
    session, icat_subscriber, icat_logbook_subscriber, esrf_data_policy
):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    default_proposal = f"{scan_saving.beamline}{time.strftime('%y%m')}"

    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    create_dataset(scan_saving)

    newproposal("toto")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "toto", category="info"
    )
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == "toto"
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    create_dataset(scan_saving)

    newcollection("tata")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "tata", category="info"
    )
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == "toto"
    assert scan_saving.collection_name == "tata"
    assert scan_saving.dataset_name == "0001"
    create_dataset(scan_saving)

    newdataset("tutu")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "tutu", category="info"
    )
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == "toto"
    assert scan_saving.collection_name == "tata"
    assert scan_saving.dataset_name == "tutu"
    create_dataset(scan_saving)

    newproposal()
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, default_proposal, category="info"
    )
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0002"
    create_dataset(scan_saving)

    enddataset()
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0003"
    create_dataset(scan_saving)

    endproposal()
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0004"
    create_dataset(scan_saving)

    newproposal("toto")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "toto", category="info"
    )
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    assert scan_saving.proposal_name == "toto"
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0002"
    create_dataset(scan_saving)

    endproposal()
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0005"


def test_data_policy_repeat_user_functions(
    session, icat_subscriber, icat_logbook_subscriber, esrf_data_policy
):
    scan_saving = session.scan_saving
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    default_proposal = f"{scan_saving.beamline}{time.strftime('%y%m')}"

    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    assert scan_saving.collection.sample_description is None
    assert scan_saving.dataset.description is None

    scan_saving.newproposal(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, default_proposal, category="info"
    )
    scan_saving.newcollection(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "sample", category="info"
    )
    scan_saving.newdataset(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0001", category="info"
    )

    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    assert scan_saving.collection.sample_description is None
    assert scan_saving.dataset.description is None

    scan_saving.newsample(None, description="sample description")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "sample", category="info"
    )
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    assert scan_saving.collection.sample_description == "sample description"
    assert scan_saving.dataset.description == "sample description"

    scan_saving.newsample(None, description="modified sample description")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "sample", category="info"
    )
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    assert scan_saving.collection.sample_description == "modified sample description"
    assert scan_saving.dataset.description == "modified sample description"

    scan_saving.newdataset(None, description="toto")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0001", category="info"
    )
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"
    assert scan_saving.collection.sample_description == "modified sample description"
    assert scan_saving.dataset.description == "modified sample description (toto)"


def test_fresh_sample(session, esrf_data_policy):
    scan_saving = ScanSaving("my_custom_scansaving")
    scan_saving.newsample("toto")
    assert scan_saving.collection_name == "toto"
    assert scan_saving.dataset_name == "0001"


def test_fresh_newcollection(session, esrf_data_policy):
    scan_saving = ScanSaving("my_custom_scansaving")
    scan_saving.newcollection("toto")
    assert scan_saving.collection_name == "toto"
    assert scan_saving.dataset_name == "0001"


def test_fresh_newdataset(session, esrf_data_policy):
    scan_saving = ScanSaving("my_custom_scansaving")
    scan_saving.newdataset("toto")
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "toto"


def test_data_policy_name_validation(session, esrf_data_policy):
    scan_saving = session.scan_saving

    for name in ("with,", "with:", "with;"):
        with pytest.raises(ValueError):
            scan_saving.proposal_name = name
        with pytest.raises(ValueError):
            scan_saving.collection_name = name
        with pytest.raises(ValueError):
            scan_saving.dataset_name = name

    for name in (" HG- 64", "HG__64", "hg_64", "  H -- G   -- 6_4  "):
        scan_saving.proposal_name = name
        assert scan_saving.proposal_name == "hg64"

    for name in (" sample Name", "sample  Name", "  sample -- Name "):
        scan_saving.collection_name = name
        assert scan_saving.collection_name == "sample_Name"

    for name in (" dataset Name", "dataset  Name", "  dataset -- Name "):
        scan_saving.dataset_name = name
        assert scan_saving.dataset_name == "dataset_Name"


def test_session_scan_saving_clone(session, esrf_data_policy):
    scan_saving = session.scan_saving

    # just to create a tango dev proxy in scan saving
    scan_saving.icat_proxy

    # create a clone
    scan_saving2 = scan_saving.clone()

    # check that the clone is a clone
    # and that the SLOTS are the same (shallow copy)
    assert id(scan_saving) != id(scan_saving2)
    assert scan_saving2._icat_proxy is not None
    assert id(scan_saving._icat_proxy) == id(scan_saving2._icat_proxy)

    # check that the same redis structure is used by the clone
    scan_saving.proposal_name = "toto"
    assert scan_saving2.proposal_name == "toto"


def test_mount_points(session, esrf_data_policy):
    scan_saving = session.scan_saving
    scan_saving_config = esrf_data_policy

    # Test setting mount points
    assert scan_saving.mount_points == {"", "fs1", "fs2", "fs3"}
    for mp in ["", "fs1", "fs2", "fs3"]:
        scan_saving.mount_point = mp
        assert scan_saving.mount_point == mp
    with pytest.raises(ValueError):
        scan_saving.mount_point = "non-existing"
    scan_saving.mount_point == mp

    # Test temp mount points (has sf1 and sf2 and fixed icat)
    scan_saving.proposal_name = "temp123"

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
    scan_saving.proposal_name = "hg123"

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
    scan_saving.proposal_name = "blc123"

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
    session, icat_subscriber, icat_logbook_subscriber, esrf_data_policy
):
    scan_saving = session.scan_saving
    default_proposal = f"{scan_saving.beamline}{time.strftime('%y%m')}"
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    scan_saving.newproposal("hg123")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "hg123", category="info"
    )
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    scan_saving.newcollection("sample1")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "sample1", category="info"
    )
    create_dataset(scan_saving)

    assert scan_saving.proposal_name == "hg123"
    assert scan_saving.collection_name == "sample1"
    assert scan_saving.dataset_name == "0001"
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )

    scan_saving.enddataset()
    assert scan_saving.proposal_name == "hg123"
    assert scan_saving.collection_name == "sample1"
    assert scan_saving.dataset_name == "0002"
    create_dataset(scan_saving)
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )

    scan_saving.endproposal()
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    assert scan_saving.proposal_name == default_proposal
    assert scan_saving.collection_name == "sample"
    assert scan_saving.dataset_name == "0001"


def test_data_policy_event(session, esrf_data_policy):
    e = channels.EventChannel(f"{session.name}:esrf_data_policy")
    full_event_list = list()
    called_cbk = {"nb": 0}
    called = gevent.event.Event()

    def f(events_list):
        # global last_event
        called_cbk["nb"] += 1
        full_event_list.extend(events_list)
        called.set()

    e.register_callback(f)

    def wait_for_event_callback():
        # give the hand to gevent loop and wait callback to be called
        with gevent.Timeout(1):
            called.wait()
            called.clear()

    scan_saving = session.scan_saving

    wait_for_event_callback()
    assert called_cbk["nb"] == 1
    assert full_event_list[-1]["event_type"] == ESRFDataPolicyEvent.Enable

    scan_saving.newproposal("hg123")
    wait_for_event_callback()
    assert called_cbk["nb"] == 2
    assert full_event_list[-1]["event_type"] == ESRFDataPolicyEvent.Change
    assert full_event_list[-1]["value"]["message"] == "Proposal set to 'hg123'"
    scan_saving.newcollection("sample1")
    scan_saving.newdataset("42")
    create_dataset(scan_saving)

    scan_saving.enddataset()
    create_dataset(scan_saving)

    scan_saving.endproposal()
    wait_for_event_callback()
    assert len(full_event_list) == 5
    wait_for_event_callback()

    session.disable_esrf_data_policy()
    wait_for_event_callback()
    assert full_event_list[-1]["event_type"] == ESRFDataPolicyEvent.Disable


def test_date_in_basepath(session, icat_logbook_subscriber, esrf_data_policy):
    # Put date in base path template:
    scan_saving = session.scan_saving
    new_base_path = os.path.join(scan_saving.base_path, "{date}")
    scan_saving.scan_saving_config["inhouse_data_root"] = new_base_path

    # Call newproposal in the past:
    pasttime = time.time() - 3600 * 24 * 100

    def mytime():
        return pasttime

    time.time, orgtime = mytime, time.time
    try:
        scan_saving.newproposal("ihch123")
        icat_test_utils.assert_logbook_received(
            icat_logbook_subscriber, "ihch123", category="info"
        )
        past = scan_saving.date
        assert scan_saving.base_path.endswith(past)
    finally:
        time.time = orgtime

    # Call newproposal in the present:
    scan_saving.newproposal("ihch123")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "ihch123", category="info"
    )
    assert scan_saving.date == past
    assert scan_saving.base_path.endswith(past)

    scan_saving.newproposal("ihch456")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "ihch456", category="info"
    )
    assert scan_saving.date != past
    assert not scan_saving.base_path.endswith(past)

    scan_saving.newproposal("ihch123")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "ihch123", category="info"
    )
    assert scan_saving.date != past
    assert not scan_saving.base_path.endswith(past)


def test_parallel_sessions(
    session,
    session2,
    icat_subscriber,
    icat_logbook_subscriber,
    esrf_data_policy,
    esrf_data_policy2,
):
    # SCAN_SAVING uses the `current_session`

    def get_scan_saving1():
        set_current_session(session, force=True)
        return session.scan_saving

    def get_scan_saving2():
        set_current_session(session2, force=True)
        return session2.scan_saving

    scan_saving = get_scan_saving1()
    assert scan_saving.session == "test_session"
    assert scan_saving.dataset_name == "0001"
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    scan_saving = get_scan_saving2()
    assert scan_saving.session == "test_session2"
    assert scan_saving.dataset_name == "0002"
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)

    scan_saving = get_scan_saving1()
    scan_saving.newproposal("blc123")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "blc123", category="info"
    )
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    assert scan_saving.dataset_name == "0001"

    scan_saving = get_scan_saving2()
    scan_saving.newproposal("blc123")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "blc123", category="info"
    )
    icat_test_utils.assert_icat_received_current_proposal(scan_saving, icat_subscriber)
    assert scan_saving.dataset_name == "0002"

    get_scan_saving1().newdataset(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0001", category="info"
    )
    get_scan_saving2().newdataset(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0002", category="info"
    )
    assert get_scan_saving1().dataset_name == "0001"
    assert get_scan_saving2().dataset_name == "0002"

    get_scan_saving2().newdataset(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0002", category="info"
    )
    get_scan_saving1().newdataset(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0001", category="info"
    )
    assert get_scan_saving1().dataset_name == "0001"
    assert get_scan_saving2().dataset_name == "0002"

    scan_saving = get_scan_saving1()
    expected_dataset = icat_test_utils.expected_icat_mq_message(
        scan_saving, dataset=True
    )
    create_dataset(scan_saving)
    scan_saving.newdataset(None)
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0003", category="info"
    )
    icat_test_utils.assert_icat_received(icat_subscriber, expected_dataset)
    assert get_scan_saving1().dataset_name == "0003"
    assert get_scan_saving2().dataset_name == "0002"

    get_scan_saving1().newdataset("0002")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "0003", category="info"
    )
    assert get_scan_saving1().dataset_name == "0003"
    assert get_scan_saving2().dataset_name == "0002"

    get_scan_saving1().newdataset("named")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "named", category="info"
    )
    assert get_scan_saving1().dataset_name == "named"
    assert get_scan_saving2().dataset_name == "0002"

    get_scan_saving2().newdataset("named")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "named_0002", category="info"
    )
    assert get_scan_saving1().dataset_name == "named"
    assert get_scan_saving2().dataset_name == "named_0002"


def test_elog_print(session, icat_logbook_subscriber, esrf_data_policy):
    elog_print("message1")
    icat_test_utils.assert_logbook_received(
        icat_logbook_subscriber, "message1", complete=True, category="comment"
    )


def test_electronic_logbook(session, icat_logbook_subscriber, esrf_data_policy):
    lst = [
        ("info", "info"),
        ("warning", "error"),
        ("error", "error"),
        ("debug", "debug"),
        ("critical", "error"),
        ("command", "commandLine"),
        ("comment", "comment"),
        ("print", "comment"),
    ]
    scan_saving = session.scan_saving
    for method_name, category in lst:
        msg = repr(method_name + " message")
        method = getattr(logtools.elogbook, method_name)
        method(msg)
        icat_test_utils.assert_logbook_received(
            icat_logbook_subscriber,
            msg,
            complete=True,
            category=category,
            scan_saving=scan_saving,
        )


def test_parallel_scans(session, esrf_data_policy):
    glts = [
        gevent.spawn(session.scan_saving.clone().on_scan_run, True) for _ in range(100)
    ]
    gevent.joinall(glts, raise_error=True, timeout=10)


@pytest.mark.parametrize(
    "missing_dataset, missing_collection, missing_proposal, policymethod",
    list(
        itertools.product(
            [True, False],
            [True, False],
            [True, False],
            [newdataset, newsample, newproposal],
        )
    ),
)
def test_missing_icat_nodes_not_blocking(
    missing_dataset,
    missing_collection,
    missing_proposal,
    policymethod,
    session,
    esrf_data_policy,
    nexus_writer_service,
):
    diode = session.config.get("diode")
    scan_saving = session.scan_saving

    s = loopscan(1, .001, diode)

    old_dataset = scan_saving.dataset
    assert not old_dataset.is_closed

    if missing_dataset:
        dataset = scan_saving.dataset.node
        s.root_connection.delete(dataset.db_name)
    if missing_collection:
        collection = scan_saving.collection.node
        s.root_connection.delete(collection.db_name)
    if missing_proposal:
        proposal = scan_saving.proposal.node
        s.root_connection.delete(proposal.db_name)

    # Check that the dataset is closed despite the exception
    # due to missing nodes (i.e. incomplete ICAT metadata)
    if missing_dataset or missing_collection or missing_proposal:
        with pytest.raises(
            RuntimeError,
            match="The dataset was closed but its ICAT metadata is incomplete",
        ):
            policymethod("new")
        assert old_dataset.is_closed

    # Check that the session is not blocked
    policymethod("new")
