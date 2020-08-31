# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import os
from bliss.common.standard import loopscan, mv
from bliss.common.utils import rounder
from bliss.common.tango import DevFailed
from bliss.common.session import set_current_session
from bliss.shell.standard import (
    newproposal,
    newsample,
    newdataset,
    enddataset,
    endproposal,
    lprint,
)


def icat_info(scan_saving, dataset=False):
    """Information expected to be received by ICAT
    """
    url = "http://www.esrf.fr/icat"
    if dataset:
        start = f'<tns:dataset xmlns:tns="{url}" complete="true">'
        end = "</tns:dataset>"
        exptag = "investigation"
    else:
        start = f'<tns:investigation xmlns:tns="{url}">'
        end = "</tns:investigation>"
        exptag = "experiment"
    proposal = f"<tns:{exptag}>{scan_saving.proposal}</tns:{exptag}>"
    beamline = f"<tns:instrument>{scan_saving.beamline}</tns:instrument>"
    info = {"start": start, "end": end, "proposal": proposal, "beamline": beamline}
    if dataset:
        info["dataset"] = f"<tns:name>{scan_saving.dataset}</tns:name>"
        info[
            "sample"
        ] = f'<tns:sample xmlns:tns="{url}"><tns:name>{scan_saving.sample}</tns:name></tns:sample>'
        info["path"] = f"<tns:location>{scan_saving.icat_root_path}</tns:location>"
    return info


def assert_icat_received(icat_subscriber, expected, dataset=None, timeout=10):
    """Check whether ICAT received the correct information
    """
    print("\nWaiting of ICAT message ...")
    icat_received = icat_subscriber.get(timeout=timeout)
    print(f"Validating ICAT message: {icat_received}")
    for k, v in expected.items():
        if k == "start":
            assert icat_received.startswith(v), k
        elif k == "end":
            assert icat_received.endswith(v), k
        else:
            assert v in icat_received, k


def assert_logbook_received(icat_logbook_server, messages, timeout=10, complete=False):
    _, queue = icat_logbook_server
    print("\nWaiting of ICAT logbook message ...")
    logbook_received = queue.get(timeout=timeout)
    print(f"Validating ICAT logbook message: {logbook_received}")
    content = logbook_received["content"]
    if isinstance(messages, str):
        messages = [messages]
    for message, adict in zip(messages, content):
        if complete:
            assert adict["text"] == message
        else:
            assert message in adict["text"]


def test_stomp_server(icat_publisher, icat_subscriber):
    icat_publisher.sendall(b"MYMESSAGE1\nMYMESSAGE2\n")
    assert icat_subscriber.get(timeout=5) == "MYMESSAGE1"
    assert icat_subscriber.get(timeout=5) == "MYMESSAGE2"


def test_jolokia_server(jolokia_server):
    # TODO: send test request
    pass


def test_icat_logbook_server(icat_logbook_server):
    # TODO: send test request
    pass


def test_icat_backend(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
    icat_logbook_server,
):
    mdexp_dev_fqdn, mdexp_dev = metaexp_with_backend
    mdmgr_dev_fqdn, mdmgr_dev = metamgr_with_backend
    port, log_messages = icat_logbook_server
    scan_saving = session.scan_saving
    scan_saving.writer = "hdf5"

    diode = session.config.get("diode")
    newproposal("totoproposal")
    expected = icat_info(scan_saving)
    assert_icat_received(icat_subscriber, expected)
    assert_logbook_received(icat_logbook_server, "Proposal set to")

    newdataset()
    loopscan(1, .1, diode)
    assert_logbook_received(icat_logbook_server, "Dataset set to")
    expected = icat_info(scan_saving, dataset=True)
    enddataset()
    assert_icat_received(icat_subscriber, expected)


def test_inhouse_scan_saving(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
):
    scan_saving = session.scan_saving
    scan_saving_config = esrf_data_policy
    for bset in [False, True]:
        if bset:
            scan_saving.proposal = "blc123"
        assert scan_saving.beamline == scan_saving_config["beamline"]
        if bset:
            assert scan_saving.proposal == "blc123"
        else:
            assert (
                scan_saving.proposal == f"{scan_saving.beamline}{time.strftime('%y%m')}"
            )
        assert scan_saving.base_path == scan_saving_config["inhouse_data_root"].format(
            beamline=scan_saving.beamline
        )
        assert scan_saving.icat_base_path == scan_saving_config[
            "inhouse_data_root"
        ].format(beamline=scan_saving.beamline)
        assert_default_sample_dataset(scan_saving)
        expected = icat_info(scan_saving)
        assert_icat_received(icat_subscriber, expected)


def test_visitor_scan_saving(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
):
    scan_saving = session.scan_saving
    scan_saving.mount_point = "fs1"
    scan_saving_config = esrf_data_policy
    scan_saving.proposal = "mx415"
    assert scan_saving.base_path == scan_saving_config["visitor_data_root"]["fs1"]
    assert scan_saving.icat_base_path == scan_saving_config["visitor_data_root"]["fs1"]
    assert_default_sample_dataset(scan_saving)
    expected = icat_info(scan_saving)
    assert_icat_received(icat_subscriber, expected)


def test_tmp_scan_saving(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
):
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
    assert_default_sample_dataset(scan_saving)
    expected = icat_info(scan_saving)
    assert_icat_received(icat_subscriber, expected)


def assert_default_sample_dataset(scan_saving):
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
    scan_saving.dataset = ""
    assert scan_saving.dataset == "0001"
    with pytest.raises(AttributeError):
        scan_saving.template = ""
    assert scan_saving.get_path().endswith("0001")


def create_dataset(scan_saving):
    """Create the dataset on disk
    """
    paths = [scan_saving.root_path, scan_saving.icat_root_path]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)


def test_auto_dataset_increment(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
):
    scan_saving = session.scan_saving
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.dataset == "0001"

    create_dataset(scan_saving)
    scan_saving.dataset = ""
    assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.dataset == "0002"

    create_dataset(scan_saving)
    path = scan_saving.get_path()
    new_filename = os.path.join(path, scan_saving.data_filename + ".h5")
    with open(new_filename, "w") as f:
        scan_saving.dataset = ""
        assert_icat_received(icat_subscriber, expected_dataset)
        expected_dataset = icat_info(scan_saving, dataset=True)
        assert scan_saving.dataset == "0003"
        # create_dataset(scan_saving)

    scan_saving.dataset = "dataset"
    # No directory -> not in ICAT
    # assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)

    create_dataset(scan_saving)
    scan_saving.dataset = "dataset"
    assert_icat_received(icat_subscriber, expected_dataset)
    assert scan_saving.dataset == "dataset_0002"
    assert scan_saving.get_path().endswith("dataset_0002")


def test_data_policy_scan_check_servers(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    nexus_writer_service,
    icat_subscriber,
):
    scan_saving = session.scan_saving
    mdexp_dev_fqdn, mdexp_dev = metaexp_with_backend
    mdmgr_dev_fqdn, mdmgr_dev = metamgr_with_backend
    diode = session.env_dict["diode"]

    expected = {
        "proposal": "",
        "sample": None,
        "dataset": None,
        "path": None,
        "state": "OFF",
    }
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.proposal = "proposal1"
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    expected["proposal"] = "proposal1"
    expected["state"] = "STANDBY"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.sample = "sample1"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.dataset = "dataset1"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    loopscan(3, 0.01, diode)
    assert_servers(mdexp_dev, mdmgr_dev, **expected)
    expected_dataset = icat_info(scan_saving, dataset=True)

    expected["path"] = session.scan_saving.icat_root_path
    scan_saving.dataset = "dataset2"
    assert_icat_received(icat_subscriber, expected_dataset)
    expected["sample"] = "sample1"
    expected["dataset"] = ""
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.dataset = "dataset2"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.dataset = "dataset3"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.sample = "sample2"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    loopscan(3, 0.01, diode)
    assert_servers(mdexp_dev, mdmgr_dev, **expected)
    expected_dataset = icat_info(scan_saving, dataset=True)

    expected["path"] = session.scan_saving.icat_root_path
    scan_saving.dataset = ""
    assert_icat_received(icat_subscriber, expected_dataset)
    expected["sample"] = "sample2"
    assert_servers(mdexp_dev, mdmgr_dev, **expected)

    scan_saving.proposal = "proposal2"
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
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


def test_data_policy_user_functions(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
    icat_logbook_server,
):
    scan_saving = session.scan_saving
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    expected_dataset = icat_info(scan_saving, dataset=True)
    default_proposal = f"{scan_saving.beamline}{time.strftime('%y%m')}"

    assert scan_saving.proposal == default_proposal
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    create_dataset(scan_saving)

    newproposal("toto")
    assert_logbook_received(icat_logbook_server, "toto")
    assert_icat_received(icat_subscriber, expected_dataset)
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"
    create_dataset(scan_saving)

    newsample("tata")
    assert_logbook_received(icat_logbook_server, "tata")
    assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "tata"
    assert scan_saving.dataset == "0001"
    create_dataset(scan_saving)

    newdataset("tutu")
    assert_logbook_received(icat_logbook_server, "tutu")
    assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "tata"
    assert scan_saving.dataset == "tutu"
    create_dataset(scan_saving)

    newproposal()
    assert_logbook_received(icat_logbook_server, default_proposal)
    assert_icat_received(icat_subscriber, expected_dataset)
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == default_proposal
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0002"
    create_dataset(scan_saving)

    enddataset()
    assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == default_proposal
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0003"
    create_dataset(scan_saving)

    endproposal()
    assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == default_proposal
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0004"
    create_dataset(scan_saving)

    newproposal("toto")
    assert_logbook_received(icat_logbook_server, "toto")
    assert_icat_received(icat_subscriber, expected_dataset)
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    expected_dataset = icat_info(scan_saving, dataset=True)
    assert scan_saving.proposal == "toto"
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0002"
    create_dataset(scan_saving)

    endproposal()
    assert_icat_received(icat_subscriber, expected_dataset)
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    assert scan_saving.proposal == default_proposal
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0005"


def test_data_policy_name_validation(
    session, esrf_data_policy, metaexp_with_backend, metamgr_with_backend
):
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
    session, esrf_data_policy, metaexp_with_backend, metamgr_with_backend
):
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
    scan_saving.proposal = "toto"
    assert scan_saving2.proposal == "toto"


def test_mount_points(
    session, esrf_data_policy, metaexp_with_backend, metamgr_with_backend
):
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
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
    icat_logbook_server,
):
    mdexp_dev_fqdn, mdexp_dev = metaexp_with_backend
    mdmgr_dev_fqdn, mdmgr_dev = metamgr_with_backend
    scan_saving = session.scan_saving
    default_proposal = f"{scan_saving.beamline}{time.strftime('%y%m')}"

    scan_saving.newproposal("hg123")
    assert_logbook_received(icat_logbook_server, "hg123")
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    scan_saving.newsample("sample1")
    assert_logbook_received(icat_logbook_server, "sample1")
    create_dataset(scan_saving)
    assert scan_saving.proposal == "hg123"
    assert scan_saving.sample == "sample1"
    assert scan_saving.dataset == "0001"
    expected_dataset = icat_info(scan_saving, dataset=True)

    scan_saving.enddataset()
    assert scan_saving.proposal == "hg123"
    assert scan_saving.sample == "sample1"
    assert scan_saving.dataset == "0002"
    create_dataset(scan_saving)
    assert_icat_received(icat_subscriber, expected_dataset)
    expected_dataset = icat_info(scan_saving, dataset=True)

    scan_saving.endproposal()
    assert_icat_received(icat_subscriber, expected_dataset)
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    assert scan_saving.proposal == default_proposal
    assert scan_saving.sample == "sample"
    assert scan_saving.dataset == "0001"


def test_date_in_basepath(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_logbook_server,
):
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
        assert_logbook_received(icat_logbook_server, "ihch123")
        past = scan_saving.date
        assert scan_saving.base_path.endswith(past)
    finally:
        time.time = orgtime

    # Call newproposal in the present:
    scan_saving.newproposal("ihch123")
    assert_logbook_received(icat_logbook_server, "ihch123")
    assert scan_saving.date == past
    assert scan_saving.base_path.endswith(past)

    scan_saving.newproposal("ihch456")
    assert_logbook_received(icat_logbook_server, "ihch456")
    assert scan_saving.date != past
    assert not scan_saving.base_path.endswith(past)

    scan_saving.newproposal("ihch123")
    assert_logbook_received(icat_logbook_server, "ihch123")
    assert scan_saving.date != past
    assert not scan_saving.base_path.endswith(past)


def test_parallel_sessions(
    beacon,
    session,
    session2,
    esrf_data_policy,
    esrf_data_policy2,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_subscriber,
    icat_logbook_server,
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
    assert scan_saving.dataset == "0001"
    assert_icat_received(icat_subscriber, icat_info(scan_saving))

    scan_saving = get_scan_saving2()
    assert scan_saving.session == "test_session2"
    assert scan_saving.dataset == "0002"
    assert_icat_received(icat_subscriber, icat_info(scan_saving))

    scan_saving = get_scan_saving1()
    scan_saving.newproposal("blc123")
    assert_logbook_received(icat_logbook_server, "blc123")
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    assert scan_saving.dataset == "0001"

    scan_saving = get_scan_saving2()
    scan_saving.newproposal("blc123")
    assert_logbook_received(icat_logbook_server, "blc123")
    assert_icat_received(icat_subscriber, icat_info(scan_saving))
    assert scan_saving.dataset == "0002"

    get_scan_saving1().newdataset(None)
    assert_logbook_received(icat_logbook_server, "0001")
    get_scan_saving2().newdataset(None)
    assert_logbook_received(icat_logbook_server, "0002")
    assert get_scan_saving1().dataset == "0001"
    assert get_scan_saving2().dataset == "0002"

    get_scan_saving2().newdataset(None)
    assert_logbook_received(icat_logbook_server, "0002")
    get_scan_saving1().newdataset(None)
    assert_logbook_received(icat_logbook_server, "0001")
    assert get_scan_saving1().dataset == "0001"
    assert get_scan_saving2().dataset == "0002"

    scan_saving = get_scan_saving1()
    expected_dataset = icat_info(scan_saving, dataset=True)
    create_dataset(scan_saving)
    scan_saving.newdataset(None)
    assert_logbook_received(icat_logbook_server, "0003")
    assert_icat_received(icat_subscriber, expected_dataset)
    assert get_scan_saving1().dataset == "0003"
    assert get_scan_saving2().dataset == "0002"

    get_scan_saving1().newdataset("0002")
    assert_logbook_received(icat_logbook_server, "0003")
    assert get_scan_saving1().dataset == "0003"
    assert get_scan_saving2().dataset == "0002"

    get_scan_saving1().newdataset("named")
    assert_logbook_received(icat_logbook_server, "named")
    assert get_scan_saving1().dataset == "named"
    assert get_scan_saving2().dataset == "0002"

    get_scan_saving2().newdataset("named")
    assert_logbook_received(icat_logbook_server, "named_0002")
    assert get_scan_saving1().dataset == "named"
    assert get_scan_saving2().dataset == "named_0002"


def test_lprint(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_logbook_server,
):
    lprint("message1")
    assert_logbook_received(icat_logbook_server, "message1", complete=True)


def test_lprint_move_axis(
    session,
    esrf_data_policy,
    metaexp_with_backend,
    metamgr_with_backend,
    icat_logbook_server,
):
    mot = session.env_dict.get("s1hg")
    a = mot.position
    b = 10
    mv(mot, a)
    # No logbook messages because we are already on "a"

    def as_string(p):
        return rounder(mot.tolerance, p)

    for _ in range(10):
        mv(mot, b)
        mv_msg = f"Moving s1hg from {as_string(a)} to {as_string(b)}"
        assert_logbook_received(icat_logbook_server, mv_msg, complete=True)
        assert_logbook_received(icat_logbook_server, "Moving s1f")
        assert_logbook_received(icat_logbook_server, "Moving s1b")
        a, b = b, a
