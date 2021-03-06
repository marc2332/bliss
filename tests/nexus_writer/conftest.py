# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
import gevent
from gevent import subprocess
from contextlib import contextmanager
from bliss.common import measurementgroup
from bliss.common.tango import DevState, Database
from nexus_writer_service.subscribers.session_writer import all_cli_saveoptions
from bliss.tango.clients.utils import wait_tango_device

from tests.nexus_writer.helpers import nxw_test_config
from tests.nexus_writer.helpers import nxw_test_utils


@pytest.fixture
def nexus_writer_session(
    beacon, lima_simulator, lima_simulator2, machinfo_tango_server
):
    """Writer sessions with lots of different detectors and scan types
    """
    session = beacon.get("nexus_writer_session")
    session.setup()
    yield session
    session.close()


@pytest.fixture
def nexus_writer_session_policy(
    beacon, nexus_writer_session, metaexp_without_backend, metamgr_without_backend
):
    """Writer sessions with lots of different detectors and scan types
    """
    yield nexus_writer_session


@pytest.fixture
def nexus_writer_base(nexus_writer_session_policy, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session_policy, scan_tmpdir, config=False, alt=False, policy=True
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
def nexus_writer_base_alt(nexus_writer_session_policy, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session_policy, scan_tmpdir, config=False, alt=True, policy=True
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_config(nexus_writer_session_policy, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session_policy, scan_tmpdir, config=True, alt=False, policy=True
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_config_capture(nexus_writer_session_policy, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session_policy,
        scan_tmpdir,
        config=True,
        alt=False,
        policy=True,
        capture=True,
    ) as info:
        yield info


@pytest.fixture
def nexus_writer_limited_disk_space(nexus_writer_session_policy, scan_tmpdir):
    """Like nexus_writer_config but require more disk space
    than available.
    """
    statvfs = os.statvfs(scan_tmpdir)
    free_space = statvfs.f_frsize * statvfs.f_bavail / 1024 ** 2
    with nexus_writer(
        nexus_writer_session_policy,
        scan_tmpdir,
        config=True,
        alt=False,
        policy=True,
        required_disk_space=free_space * 10,
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
def nexus_writer_config_alt(nexus_writer_session_policy, scan_tmpdir):
    """Writer session with a Nexus writer
    """
    with nexus_writer(
        nexus_writer_session_policy, scan_tmpdir, config=True, alt=True, policy=True
    ) as info:
        yield info


@contextmanager
def nexus_writer(
    session,
    tmpdir,
    config=True,
    alt=False,
    policy=True,
    capture=False,
    required_disk_space=None,
):
    """Nexus writer for this session

    :param session:
    :param tmpdir:
    :param bool policy:
    :param bool config:
    :param bool alt:
    :param bool capture:
    :param num required_disk_space:
    :returns dict:
    """
    info = {
        "session": session,
        "tmpdir": tmpdir,
        "config": config,
        "alt": alt,
        "policy": policy,
        "required_disk_space": required_disk_space,
    }
    prepare_objects(**info)
    prepare_scan_saving(**info)
    with writer_tango(capture=capture, **info) as writer:
        info["writer"] = writer
        yield info


def prepare_objects(session=None, **kwargs):
    att1 = session.env_dict["att1"]
    att1.Al()
    beamstop = session.env_dict["beamstop"]
    beamstop.IN()


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
        roots = ["inhouse_data_root", "visitor_data_root", "tmp_data_root"]
        for root in roots:
            for prefix in ["", "icat_"]:
                key = prefix + root
                mount_points = scan_saving_config.get(key, None)
                if mount_points is None:
                    continue
                elif isinstance(mount_points, str):
                    scan_saving_config[key] = mount_points.replace("/tmp/scans", tmpdir)
                else:
                    for mp in mount_points:
                        mount_points[mp] = mount_points[mp].replace(
                            "/tmp/scans", tmpdir
                        )
        scan_saving.proposal_name = "testproposal"
        technique = nxw_test_config.technique["withpolicy"]
        scan_saving.proposal.all.definition = technique
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
def writer_tango(
    session=None,
    tmpdir=None,
    config=True,
    alt=False,
    capture=False,
    required_disk_space=None,
    **kwargs,
):
    """
    Run external writer as a Tango server

    :param session:
    :param tmpdir:
    :param callable wait_for_fixture:
    :param bool config:
    :param bool alt:
    :param bool capture:
    :param num required_disk_space:
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
    properties, attributes = writer_options(
        tango=True, config=config, alt=alt, required_disk_space=required_disk_space
    )
    db = Database()
    db.put_device_property(device_name, properties)
    exception = None
    for i in range(3):
        with nxw_test_utils.popencontext(cliargs, env=env, capture=capture) as greenlet:
            try:
                dev_proxy = wait_tango_device(
                    device_fqdn=device_fqdn, state=DevState.ON
                )
            except Exception as e:
                exception = e
                continue
            # Changing attributes does not need Init
            for attr, value in attributes.items():
                dev_proxy.write_attribute(attr, value)

            # DEBUG(1), INFO(2), WARNING(3), ...
            assert int(dev_proxy.writer_log_level) == 3
            assert int(dev_proxy.tango_log_level) == 3

            greenlet.proxy = dev_proxy
            try:
                yield greenlet
            finally:
                break
    else:
        raise RuntimeError(f"Could not start {device_fqdn}") from exception


@contextmanager
def writer_process(
    session=None, tmpdir=None, config=True, alt=False, capture=False, **kwargs
):
    """
    Run external writer as a python process

    :param session:
    :param tmpdir:
    :param bool config:
    :param bool alt:
    :param bool capture:
    :param kwargs: ignored
    :returns PopenGreenlet:
    """
    env = writer_env()
    cliargs = (
        ("NexusSessionWriter", session.name)
        + writer_cli_logargs(tmpdir)
        + writer_options(tango=False, config=config, alt=alt)
    )
    with nxw_test_utils.popencontext(cliargs, env=env, capture=capture) as greenlet:
        with gevent.Timeout(10, RuntimeError("Nexus Writer not running")):
            while not greenlet.stdout_contains("Start listening"):
                gevent.sleep(0.1)
        yield greenlet


def writer_options(tango=True, config=True, alt=False, required_disk_space=None):
    """
    :param bool tango: launch writer as process/tango server
    :param bool config: writer uses/ignores extra Redis info
    :param bool alt: anable all options (all disabled by default)
    :param num required_disk_space:
    """
    fixed = (
        "copy_non_external",
        "resource_profiling",
        "noconfig",
        "disable_external_hdf5",
        "required_disk_space",
    )
    options = all_cli_saveoptions(configurable=config)
    resource_profiling = options.pop("resource_profiling")["default"]
    if required_disk_space is None:
        required_disk_space = 0
    if tango:
        properties = {"copy_non_external": True}
        attributes = {}
        properties["noconfig"] = not config
        properties["required_disk_space"] = required_disk_space
        attributes["resource_profiling"] = int(resource_profiling) - 1  # to tango enum
        properties.update({k: alt for k in options if k not in fixed})
    else:
        cliargs = ["--copy_non_external"]
        if not config:
            cliargs.append("--noconfig")
        cliargs.append("--required_disk_space " + str(required_disk_space))
        cliargs.append("--resource_profiling " + resource_profiling.name)
        if alt:
            cliargs += ["--" + k for k in options if k not in fixed]
    if tango:
        return properties, attributes
    else:
        return tuple(cliargs)


def writer_cli_logargs(tmpdir):
    return (
        "--log=warning",  # applies to log_tango as well (abbreviations allowed)
        # "--redirectstdout",
        # "--redirectstderr",
        # "--logfileout={}".format(tmpdir.join("writer.stdout.log")),
        # "--logfileerr={}".format(tmpdir.join("writer.stderr.log")),
    )


def writer_env():
    env = {k: str(v) for k, v in os.environ.items()}
    # env["GEVENT_MONITOR_THREAD_ENABLE"] = "true"
    # env["GEVENT_MAX_BLOCKING_TIME"] = "1"
    return env
