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
from gevent import subprocess
from contextlib import contextmanager
from bliss.common import measurementgroup
from bliss.common.tango import DeviceProxy, DevFailed
from nexus_writer_service.utils import data_policy
from nexus_writer_service.subscribers.scan_writer_base import (
    cli_saveoptions as base_options
)
from nexus_writer_service.subscribers.scan_writer_config import (
    cli_saveoptions as config_options
)


sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))
import nxw_test_config
import nxw_test_utils


base_options = dict(base_options)
base_options.pop("copy_non_external")
base_options.pop("enable_profiling")

config_options = dict(config_options)
config_options.pop("copy_non_external")
config_options.pop("enable_profiling")

config_writer_args = (
    "--log=info",
    "--redirectstdout",
    "--redirectstderr",
    "--copy_non_external",
)
base_writer_args = config_writer_args + ("--noconfig",)
writer_tango_properties = {"copy_nonhdf5_data": True}
writer_tango_attributes = {"resource_profiling": False}


def cliargs_logfiles(cliargs, tmpdir):
    tmpdir = str(tmpdir)
    return cliargs + (
        "--logfileout={}".format(os.path.join(tmpdir, "writer.stdout.log")),
        "--logfileerr={}".format(os.path.join(tmpdir, "writer.stderr.log")),
    )


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
    measurementgroup.set_active_name(nxw_test_config.technique["withoutpolicy"] + "MG")


def scan_saving_policy(session, scan_tmpdir):
    scan_saving = session.scan_saving
    data_policy.newtmpexperiment("prop123", root=str(scan_tmpdir))
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
    cliargs = cliargs_logfiles(base_writer_args, tmpdir)
    with writer_process(session, wait_for_fixture, cliargs) as writer:
        yield {"session": session, "tmpdir": tmpdir, "writer": writer}


@pytest.fixture
def nexus_writer_base_nopolicy(nexus_base_session_nopolicy, wait_for_fixture):
    session, tmpdir = nexus_base_session_nopolicy
    cliargs = cliargs_logfiles(base_writer_args, tmpdir)
    with writer_process(session, wait_for_fixture, cliargs) as writer:
        yield {"session": session, "tmpdir": tmpdir, "writer": writer}


@pytest.fixture
def nexus_writer_base_alt(nexus_base_session_policy, wait_for_fixture):
    session, tmpdir = nexus_base_session_policy
    cliargs = cliargs_logfiles(base_writer_args, tmpdir)
    cliargs += tuple("--" + k for k in base_options if "--" + k not in cliargs)
    with writer_process(session, wait_for_fixture, cliargs) as writer:
        yield {"session": session, "tmpdir": tmpdir, "writer": writer}


@pytest.fixture
def nexus_writer_config(nexus_config_session_policy, wait_for_fixture):
    session, tmpdir = nexus_config_session_policy
    cliargs = cliargs_logfiles(config_writer_args, tmpdir)
    with writer_tango(session, wait_for_fixture, cliargs) as writer:
        yield {"session": session, "tmpdir": tmpdir, "writer": writer}


@pytest.fixture
def nexus_writer_config_nopolicy(nexus_config_session_nopolicy, wait_for_fixture):
    session, tmpdir = nexus_config_session_nopolicy
    cliargs = cliargs_logfiles(config_writer_args, tmpdir)
    with writer_tango(session, wait_for_fixture, cliargs) as writer:
        yield {"session": session, "tmpdir": tmpdir, "writer": writer}


@pytest.fixture
def nexus_writer_config_alt(nexus_config_session_policy, wait_for_fixture):
    session, tmpdir = nexus_config_session_policy
    cliargs = cliargs_logfiles(config_writer_args, tmpdir)
    cliargs += tuple("--" + k for k in config_options if "--" + k not in cliargs)
    with writer_process(session, wait_for_fixture, cliargs) as writer:
        yield {"session": session, "tmpdir": tmpdir, "writer": writer}


@contextmanager
def writer_tango(session, wait_for_fixture, cliargs):
    """
    Run external writer in a Tango server

    :param session:
    :param callable wait_for_fixture:
    :param sequence cliargs:
    :returns PopenGreenlet:
    """
    session.scan_saving.writer = "nexus"
    env = {k: str(v) for k, v in os.environ.items()}
    env["GEVENT_MONITOR_THREAD_ENABLE"] = "true"
    env["GEVENT_MAX_BLOCKING_TIME"] = "1"
    server_instance = "test"
    cliargs = ("NexusWriterService", server_instance) + cliargs
    # Register another writer with the TANGO database (testing concurrency):
    # device_fqdn = nexus_register_writer.ensure_existence(
    #    session.name, instance=server_instance, family="dummy", use_existing=False
    # )
    # Rely on beacon registration from YAML description:
    device_name = "id00/bliss_nxwriter/" + session.name
    device_fqdn = "tango://{}/{}".format(env["TANGO_HOST"], device_name)
    with nxw_test_utils.popencontext(
        cliargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
    ) as greenlet:
        with gevent.Timeout(30, RuntimeError("Nexus writer is not running")):
            while True:
                try:
                    dev_proxy = DeviceProxy(device_fqdn)
                    dev_proxy.ping()
                except DevFailed as e:
                    pass
                else:
                    break
                gevent.sleep(0.1)
        # Changing properties needs Init
        dev_proxy.set_timeout_millis(10000)
        dev_proxy.put_property(writer_tango_properties)
        dev_proxy.Init()
        # Changing attributes does not need Init
        for attr, value in writer_tango_attributes.items():
            dev_proxy.write_attribute(attr, value)
        yield greenlet


@contextmanager
def writer_process(session, wait_for_fixture, cliargs):
    """
    Run external writer in a python process

    :param session:
    :param callable wait_for_fixture:
    :param sequence cliargs:
    :returns PopenGreenlet:
    """
    session.scan_saving.writer = "hdf5"
    env = {k: str(v) for k, v in os.environ.items()}
    env["GEVENT_MONITOR_THREAD_ENABLE"] = "true"
    env["GEVENT_MAX_BLOCKING_TIME"] = "1"
    cliargs = ("NexusSessionWriter", session.name) + cliargs
    with nxw_test_utils.popencontext(
        cliargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
    ) as greenlet:
        with gevent.Timeout(30, RuntimeError("Nexus Writer not running")):
            while not greenlet.stdout_contains("Start listening"):
                gevent.sleep(0.1)
        yield greenlet
