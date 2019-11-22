# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
import sys
import gevent
from contextlib import contextmanager
from nexus_writer_service.utils import data_policy
from nexus_writer_service.scan_writers.writer_base import (
    cli_saveoptions as base_options
)
from nexus_writer_service.scan_writers.writer_config import (
    cli_saveoptions as config_options
)
from bliss.common import measurementgroup


sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))
import nxw_test_config


config_writer_args = ("--log=info",)
base_writer_args = config_writer_args + ("--noconfig",)


def setup_writer_session(session):
    session.setup()


@pytest.fixture
def nexus_base_session(beacon, lima_simulator, lima_simulator2):
    session = beacon.get("nexus_writer_base")
    setup_writer_session(session)
    yield session
    session.close()


@pytest.fixture
def nexus_config_session(beacon, lima_simulator, lima_simulator2):
    session = beacon.get("nexus_writer_config")
    setup_writer_session(session)
    yield session
    session.close()


def scan_saving_nopolicy(session, scan_tmpdir):
    scan_saving = session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    scan_saving.data_filename = "dataset"
    scan_saving.writer = "hdf5"
    measurementgroup.set_active_name(nxw_test_config.technique["withoutpolicy"] + "MG")


def scan_saving_policy(session, scan_tmpdir):
    scan_saving = session.scan_saving
    scan_saving.writer = "null"
    data_policy.newlocalexperiment("prop123", root=str(scan_tmpdir))
    scan_saving.add("sample", "sample")
    scan_saving.add("technique", nxw_test_config.technique["withpolicy"])
    scan_saving.add("dataset", "dataset")
    measurementgroup.set_active_name(scan_saving.technique + "MG")


@pytest.fixture
def nexus_base_session_policy(nexus_base_session, scan_tmpdir):
    scan_saving_policy(nexus_base_session, scan_tmpdir)
    yield nexus_base_session, scan_tmpdir


@pytest.fixture
def nexus_base_session_nopolicy(nexus_base_session, scan_tmpdir):
    scan_saving_nopolicy(nexus_base_session, scan_tmpdir)
    yield nexus_base_session, scan_tmpdir


@pytest.fixture
def nexus_config_session_policy(nexus_config_session, scan_tmpdir):
    scan_saving_policy(nexus_config_session, scan_tmpdir)
    yield nexus_config_session, scan_tmpdir


@pytest.fixture
def nexus_config_session_nopolicy(nexus_config_session, scan_tmpdir):
    scan_saving_nopolicy(nexus_config_session, scan_tmpdir)
    yield nexus_config_session, scan_tmpdir


@pytest.fixture
def nexus_writer_base(nexus_base_session_policy, wait_for_fixture):
    session, tmpdir = nexus_base_session_policy
    cliargs = "NexusSessionWriter", session.name
    cliargs += base_writer_args
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_base_alt(nexus_base_session_policy, wait_for_fixture):
    session, tmpdir = nexus_base_session_policy
    cliargs = "NexusSessionWriter", session.name
    cliargs += base_writer_args
    cliargs += tuple("--" + k for k in base_options if "--" + k not in cliargs)
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_base_nopolicy(nexus_base_session_nopolicy, wait_for_fixture):
    session, tmpdir = nexus_base_session_nopolicy
    cliargs = "NexusSessionWriter", session.name
    cliargs += base_writer_args
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_config(nexus_config_session_policy, wait_for_fixture):
    session, tmpdir = nexus_config_session_policy
    cliargs = "NexusSessionWriter", session.name
    cliargs += config_writer_args
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_config_nopolicy(nexus_config_session_nopolicy, wait_for_fixture):
    session, tmpdir = nexus_config_session_nopolicy
    cliargs = "NexusSessionWriter", session.name
    cliargs += config_writer_args
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_config_alt(nexus_config_session_policy, wait_for_fixture):
    session, tmpdir = nexus_config_session_policy
    cliargs = "NexusSessionWriter", session.name
    cliargs += config_writer_args
    cliargs += tuple("--" + k for k in config_options if "--" + k not in cliargs)
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@contextmanager
def writer_process(wait_for_fixture, cliargs):
    """
    :param callable wait_for:
    :param sequence cliargs:
    :returns Popen:
    """
    env = {k: str(v) for k, v in os.environ.items()}
    p = gevent.subprocess.Popen(
        cliargs, stdout=gevent.subprocess.PIPE, stderr=gevent.subprocess.STDOUT, env=env
    )
    with gevent.Timeout(10, RuntimeError("Nexus Writer not running")):
        wait_for_fixture(p.stdout, "Start listening to scans")
    with gevent.Timeout(1, RuntimeError("no answer from NexusSessionWriter")):
        p.stdout.read1()
    try:
        yield p.stdout
    finally:
        p.terminate()
        # TODO: not captured
        # with gevent.Timeout(10, RuntimeError("Nexus Writer did not run its cleanup")):
        #    wait_for_fixture(p.stdout, "Listener exits")
