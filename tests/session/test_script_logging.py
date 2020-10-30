# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


@pytest.fixture
def beacon_with_logging(
    beacon, capsys, caplog, log_context, log_shell_mode, icat_logbook_subscriber
):
    yield beacon


@pytest.fixture
def logging_session(beacon_with_logging):
    session = beacon_with_logging.get("test_logging_session")
    session.setup()
    yield session
    session.close()


@pytest.fixture
def logging_session_without_elogserver(beacon_with_logging):
    scan_saving_cfg = beacon_with_logging.root["scan_saving"]
    scan_saving_cfg["class"] = "ESRFScanSaving"
    session = beacon_with_logging.get("test_logging_session")
    session.setup()
    yield session
    session.close()


@pytest.fixture
def logging_session_with_elogserver(
    beacon_with_logging, metaexp_with_backend, metamgr_with_backend
):
    scan_saving_cfg = beacon_with_logging.root["scan_saving"]
    scan_saving_cfg["class"] = "ESRFScanSaving"
    session = beacon_with_logging.get("test_logging_session")
    session.setup()
    yield session
    session.close()


def check_scripts_finished(session):
    assert session.env_dict.get("setupfinished")
    assert session.env_dict.get("scriptfinished")


def check_user_logging(capsys):
    captured = capsys.readouterr().err.split("\n")
    captured = [s for s in captured if s]
    assert len(captured) == 6, captured
    expected = "ERROR: LogInitController: user error"
    assert captured[0] == expected
    expected = "LogInitController: Beacon error"
    assert expected in captured[1]
    expected = "ERROR: test_logging_session.py: user error"
    assert captured[2] == expected
    expected = "test_logging_session.py: Beacon error"
    assert expected in captured[3]
    expected = "ERROR: logscript.py: user error"
    assert captured[4] == expected
    expected = "logscript.py: Beacon error"
    assert expected in captured[5]


def check_beacon_logging(caplog):
    records = caplog.get_records("setup")
    assert len(records) == 3, records
    expected = "LogInitController: Beacon error"
    assert records[0].levelname == "ERROR"
    assert records[0].message == expected
    expected = "test_logging_session.py: Beacon error"
    assert records[1].levelname == "ERROR"
    assert records[1].message == expected
    expected = "logscript.py: Beacon error"
    assert records[2].levelname == "ERROR"
    assert records[2].message == expected


def check_elogbook(icat_logbook_subscriber):
    msginfo = icat_logbook_subscriber.get(timeout=3)
    assert msginfo["category"] == "error"
    expected = "LogInitController: E-logbook error"
    assert msginfo["content"][0]["text"] == expected
    msginfo = icat_logbook_subscriber.get(timeout=3)
    assert msginfo["category"] == "error"
    expected = "test_logging_session.py: E-logbook error"
    assert msginfo["content"][0]["text"] == expected
    msginfo = icat_logbook_subscriber.get(timeout=3)
    expected = "logscript.py: E-logbook error"
    assert msginfo["category"] == "error"
    assert msginfo["content"][0]["text"] == expected


def test_script_logging(logging_session, capsys, caplog, icat_logbook_subscriber):
    check_scripts_finished(logging_session)
    check_user_logging(capsys)
    check_beacon_logging(caplog)
    assert len(icat_logbook_subscriber) == 0


def test_script_logging_without_elogserver(
    logging_session_without_elogserver, capsys, caplog, icat_logbook_subscriber
):
    check_scripts_finished(logging_session_without_elogserver)
    check_user_logging(capsys)
    check_beacon_logging(caplog)
    assert len(icat_logbook_subscriber) == 0


def test_script_logging_with_elogserver(
    logging_session_with_elogserver, capsys, caplog, icat_logbook_subscriber
):
    check_scripts_finished(logging_session_with_elogserver)
    check_user_logging(capsys)
    check_beacon_logging(caplog)
    check_elogbook(icat_logbook_subscriber)
