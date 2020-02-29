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
from bliss.common.tango import DeviceProxy, DevFailed, DevState, Database
from nexus_writer_service.subscribers.session_writer import all_cli_saveoptions

sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))
import nxw_test_config
import nxw_test_utils


@pytest.fixture
def nexus_writer_session(
    beacon,
    metadata_experiment_tango_server,
    metadata_manager_tango_server,
    lima_simulator,
    lima_simulator2,
):
    """Writer sessions with lots of different detectors and scan types
    """
    session = beacon.get("nexus_writer_session")
    session.setup()
    yield session
    session.close()


@pytest.fixture
def nexus_writer_base(nexus_writer_session, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session, scan_tmpdir, config=False, alt=False, policy=True
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_base_nopolicy(nexus_writer_session, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session, scan_tmpdir, config=False, alt=False, policy=False
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_base_alt(nexus_writer_session, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session, scan_tmpdir, config=False, alt=True, policy=True
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_config(nexus_writer_session, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session, scan_tmpdir, config=True, alt=False, policy=True
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_config_nopolicy(nexus_writer_session, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session, scan_tmpdir, config=True, alt=False, policy=False
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_config_alt(nexus_writer_session, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session, scan_tmpdir, config=True, alt=True, policy=True
    ) as info:
        yield info


@contextmanager
def nexus_writer(session, tmpdir, config=True, alt=False, policy=True):
    """Nexus writer for this session

    :param session:
    :param tmpdir:
    :param bool policy:
    :param bool config:
    :param bool alt:
    :returns dict:
    """
    info = {
        "session": session,
        "tmpdir": tmpdir,
        "config": config,
        "alt": alt,
        "policy": policy,
    }
    prepare_scan_saving(**info)
    with writer_tango(**info) as writer:
        info["writer"] = writer
        yield info


def prepare_scan_saving(session=None, tmpdir=None, policy=True, **kwargs):
    """Initialize scan saving so the tests save in `tmpdir`
    with or without policy.

    :param session:
    :param tmpdir:
    :param bool policy:
    :param kwargs: ignored
    """
    if policy:
        tmpdir = str(tmpdir.join(session.name))
        session.enable_esrf_data_policy()
        scan_saving = session.scan_saving
        scan_saving.writer = "nexus"
        scan_saving_config = scan_saving.scan_saving_config
        for k in ["inhouse_data_root", "visitor_data_root", "tmp_data_root"]:
            scan_saving_config[k] = scan_saving_config[k].replace("/tmp/scans", tmpdir)
        scan_saving.proposal = "testproposal"
        technique = nxw_test_config.technique["withpolicy"]
        scan_saving.technique = technique
        measurementgroup.set_active_name(technique + "MG")
    else:
        tmpdir = str(tmpdir)
        session.disable_esrf_data_policy()
        scan_saving = session.scan_saving
        scan_saving.writer = "nexus"
        scan_saving.base_path = tmpdir
        scan_saving.data_filename = "{a}_{b}"
        scan_saving.add("a", "a")
        scan_saving.add("b", "b")
        technique = nxw_test_config.technique["withoutpolicy"]
        measurementgroup.set_active_name(technique + "MG")


@contextmanager
def writer_tango(session=None, tmpdir=None, config=True, alt=False, **kwargs):
    """
    Run external writer as a Tango server

    :param session:
    :param tmpdir:
    :param callable wait_for_fixture:
    :param bool config:
    :param bool alt:
    :param kwargs: ignored
    :returns PopenGreenlet:
    """
    env = writer_env()
    server_instance = "testwriters"
    cliargs = ("NexusWriterService", server_instance) + writer_cli_logargs(tmpdir)
    # Register another writer with the TANGO database (testing concurrency):
    # device_fqdn = nexus_register_writer.ensure_existence(
    #    session.name, instance=server_instance, family="dummy", use_existing=False
    # )
    # Rely on beacon registration from YAML description:
    device_name = "id00/bliss_nxwriter/" + session.name
    device_fqdn = "tango://{}/{}".format(env["TANGO_HOST"], device_name)
    properties, attributes = writer_options(tango=True, config=config, alt=alt)
    db = Database()
    db.put_device_property(device_name, properties)
    with nxw_test_utils.popencontext(
        cliargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
    ) as greenlet:
        with gevent.Timeout(10, RuntimeError("Nexus writer is not running")):
            while True:
                try:
                    dev_proxy = DeviceProxy(device_fqdn)
                    dev_proxy.ping()
                except DevFailed as e:
                    pass
                else:
                    break
                gevent.sleep(0.1)
            while dev_proxy.state() != DevState.ON:
                gevent.sleep(0.1)
        # Changing attributes does not need Init
        for attr, value in attributes.items():
            dev_proxy.write_attribute(attr, value)
        yield greenlet


@contextmanager
def writer_process(session=None, tmpdir=None, config=True, alt=False, **kwargs):
    """
    Run external writer as a python process

    :param session:
    :param tmpdir:
    :param bool config:
    :param bool alt:
    :param kwargs: ignored
    :returns PopenGreenlet:
    """
    env = writer_env()
    cliargs = (
        ("NexusSessionWriter", session.name)
        + writer_cli_logargs(tmpdir)
        + writer_options(tango=False, config=config, alt=alt)
    )
    with nxw_test_utils.popencontext(
        cliargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
    ) as greenlet:
        with gevent.Timeout(10, RuntimeError("Nexus Writer not running")):
            while not greenlet.stdout_contains("Start listening"):
                gevent.sleep(0.1)
        yield greenlet


def writer_options(tango=True, config=True, alt=False, resource_profiling=False):
    """
    :param bool tango: launch writer as process/tango server
    :param bool config: writer uses/ignores extra Redis info
    :param bool alt: anable all options (all disabled by default)
    :param bool resource_profiling:
    """
    fixed = ("copy_non_external", "resource_profiling", "noconfig")
    options = all_cli_saveoptions(configurable=config)
    if tango:
        properties = {"copy_non_external": True}
        attributes = {}
        properties["noconfig"] = not config
        attributes["resource_profiling"] = resource_profiling
        properties.update({k: alt for k in options if k not in fixed})
    else:
        cliargs = ["--copy_non_external"]
        if not config:
            cliargs.append("--noconfig")
        if resource_profiling:
            cliargs.append("--resource_profiling")
        if alt:
            cliargs += ["--" + k for k in options if k not in fixed]
    if tango:
        return properties, attributes
    else:
        return tuple(cliargs)


def writer_cli_logargs(tmpdir):
    return (
        "--log=info",
        "--redirectstdout",
        "--redirectstderr",
        "--logfileout={}".format(tmpdir.join("writer.stdout.log")),
        "--logfileerr={}".format(tmpdir.join("writer.stderr.log")),
    )


def writer_env():
    env = {k: str(v) for k, v in os.environ.items()}
    # env["GEVENT_MONITOR_THREAD_ENABLE"] = "true"
    # env["GEVENT_MAX_BLOCKING_TIME"] = "1"
    return env
