# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
import gevent
from bliss.scanning.scan_saving import set_scan_saving_class


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
def beacon_with_logging_esrf(beacon_with_logging):
    scan_saving_cfg = beacon_with_logging.root["scan_saving"]
    scan_saving_cfg["class"] = "ESRFScanSaving"
    yield beacon_with_logging
    set_scan_saving_class(None)


@pytest.fixture
def logging_session_without_elogserver(beacon_with_logging_esrf, log_directory):
    logfile = os.path.join(log_directory, "test_logging_session.log")
    with open(logfile, "w"):
        pass
    session = beacon_with_logging_esrf.get("test_logging_session")
    session.setup()
    yield session
    session.close()


@pytest.fixture
def logging_session_with_elogserver(
    beacon_with_logging_esrf, icat_backend, log_directory
):
    logfile = os.path.join(log_directory, "test_logging_session.log")
    with open(logfile, "w"):
        pass
    session = beacon_with_logging_esrf.get("test_logging_session")
    session.setup()
    yield session
    session.close()


def check_scripts_finished(session):
    assert session.env_dict.get("setupfinished")
    assert session.env_dict.get("scriptfinished")


def check_user_logging(capsys, elog_offline=False, data_policy=True):
    captured = capsys.readouterr().err.split("\n")
    captured = [s for s in captured if s]
    nexpected = 6 + elog_offline + (elog_offline and data_policy)
    assert len(captured) == nexpected, captured
    i = 0
    expected = "ERROR: LogInitController: user error"
    assert captured[i] == expected
    i += 1
    if data_policy and elog_offline:
        expected = "WARNING: The `icat_servers` beacon configuration is missing. Falling back to the deprecated ICAT tango servers."
        assert captured[i] == expected
        i += 1
    if elog_offline:
        expected = "Electronic logbook failed"
        assert expected in captured[i]
        i += 1
    expected = "LogInitController: Beacon error"
    assert expected in captured[i]
    i += 1
    expected = "ERROR: test_logging_session.py: user error"
    assert captured[i] == expected
    i += 1
    expected = "test_logging_session.py: Beacon error"
    assert expected in captured[i]
    i += 1
    expected = "ERROR: logscript.py: user error"
    assert captured[i] == expected
    i += 1
    expected = "logscript.py: Beacon error"
    assert expected in captured[i]
    i += 1


def check_beacon_logging(caplog, logfile):
    # Get lines from logging capture
    records = caplog.get_records("setup")
    assert len(records) == 3, records

    # Get lines from the log server file
    try:
        lines = []
        with gevent.Timeout(10):
            while len(lines) != 3:
                with open(logfile, "r") as f:
                    lines = [l.rstrip() for l in f]
                gevent.sleep(0.5)
    except gevent.Timeout:
        assert len(lines) == 3, lines

    expected = "LogInitController: Beacon error"
    assert records[0].levelname == "ERROR"
    assert records[0].message == expected
    assert expected in lines[0]
    expected = "test_logging_session.py: Beacon error"
    assert records[1].levelname == "ERROR"
    assert records[1].message == expected
    assert expected in lines[1]
    expected = "logscript.py: Beacon error"
    assert records[2].levelname == "ERROR"
    assert records[2].message == expected
    assert expected in lines[2]


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


def test_setup_logging_no_data_policy(
    logging_session, capsys, caplog, log_directory, icat_logbook_subscriber
):
    logfile = os.path.join(log_directory, logging_session.name + ".log")
    check_scripts_finished(logging_session)
    check_user_logging(capsys, data_policy=False)
    check_beacon_logging(caplog, logfile)
    assert len(icat_logbook_subscriber) == 0


def test_setup_logging_without_elogserver(
    logging_session_without_elogserver,
    capsys,
    caplog,
    log_directory,
    icat_logbook_subscriber,
):
    logfile = os.path.join(
        log_directory, logging_session_without_elogserver.name + ".log"
    )
    check_scripts_finished(logging_session_without_elogserver)
    check_user_logging(capsys, elog_offline=True)
    check_beacon_logging(caplog, logfile)
    assert len(icat_logbook_subscriber) == 0


def test_setup_logging_with_elogserver(
    logging_session_with_elogserver,
    capsys,
    caplog,
    log_directory,
    icat_logbook_subscriber,
):
    logfile = os.path.join(log_directory, logging_session_with_elogserver.name + ".log")
    check_scripts_finished(logging_session_with_elogserver)
    check_user_logging(capsys)
    check_beacon_logging(caplog, logfile)
    check_elogbook(icat_logbook_subscriber)
