# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
import gevent
from contextlib import contextmanager
from nexus_writer_service.utils import data_policy
from bliss.common import measurementgroup
from bliss.controllers.lima.roi import Roi as LimaRoi
from bliss.controllers.lima.lima_base import Lima
from bliss.controllers.mca.base import BaseMCA


def setup_writer_session(session):
    session.setup()
    measurementgroup.set_active_name("alldet")
    # lima_rois(session)
    mca_rois(session)


@pytest.fixture
def nexus_base_session(beacon, lima_simulator):
    session = beacon.get("nexus_writer_base")
    setup_writer_session(session)
    yield session
    session.close()


@pytest.fixture
def nexus_config_session(beacon, lima_simulator):
    session = beacon.get("nexus_writer_config")
    setup_writer_session(session)
    yield session
    session.close()


def scan_saving_withoutpolicy(session, scan_tmpdir):
    scan_saving = session.scan_saving
    scan_saving.base_path = str(scan_tmpdir)
    scan_saving.data_filename = "dataset"
    scan_saving.writer = "hdf5"


def scan_saving_withpolicy(session, scan_tmpdir):
    scan_saving = session.scan_saving
    # scan_saving.writer = 'null'  # TODO: cannot be null!!!
    data_policy.newlocalexperiment("prop123", root=str(scan_tmpdir))
    scan_saving.add("sample", "sample")
    scan_saving.add("technique", "xrfxrd")
    scan_saving.add("dataset", "dataset")


@pytest.fixture
def nexus_base_session_withpolicy(nexus_base_session, scan_tmpdir):
    scan_saving_withpolicy(nexus_base_session, scan_tmpdir)
    yield nexus_base_session, scan_tmpdir


@pytest.fixture
def nexus_base_session_withoutpolicy(nexus_base_session, scan_tmpdir):
    scan_saving_withoutpolicy(nexus_base_session, scan_tmpdir)
    yield nexus_base_session, scan_tmpdir


@pytest.fixture
def nexus_config_session_withpolicy(nexus_config_session, scan_tmpdir):
    scan_saving_withpolicy(nexus_config_session, scan_tmpdir)
    yield nexus_config_session, scan_tmpdir


@pytest.fixture
def nexus_config_session_withoutpolicy(nexus_config_session, scan_tmpdir):
    scan_saving_withoutpolicy(nexus_config_session, scan_tmpdir)
    yield nexus_config_session, scan_tmpdir


@pytest.fixture
def nexus_writer_base_withoutpolicy(nexus_base_session_withoutpolicy, wait_for_fixture):
    session, tmpdir = nexus_base_session_withoutpolicy
    cliargs = "NexusSessionWriter", session.name, "--noconfig", "--log=info"
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_base_withpolicy(nexus_base_session_withpolicy, wait_for_fixture):
    session, tmpdir = nexus_base_session_withpolicy
    cliargs = "NexusSessionWriter", session.name, "--noconfig", "--log=info"
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_config_withoutpolicy(
    nexus_config_session_withoutpolicy, wait_for_fixture
):
    session, tmpdir = nexus_config_session_withoutpolicy
    cliargs = "NexusSessionWriter", session.name, "--log=info"
    with writer_process(wait_for_fixture, cliargs) as writer_stdout:
        yield session, tmpdir, writer_stdout


@pytest.fixture
def nexus_writer_config_withpolicy(nexus_config_session_withpolicy, wait_for_fixture):
    session, tmpdir = nexus_config_session_withpolicy
    cliargs = "NexusSessionWriter", session.name, "--log=info"
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


def objects_of_type(session, *classes):
    ret = {}
    for name in session.object_names:
        try:
            obj = session.env_dict[name]
        except KeyError:
            continue
        if isinstance(obj, classes):
            ret[name] = obj
    return ret


def lima_rois(session):
    rois = {
        "roi1": LimaRoi(0, 0, 100, 200),
        "roi2": LimaRoi(10, 20, 200, 500),
        "roi3": LimaRoi(20, 60, 500, 500),
        "roi4": LimaRoi(60, 20, 50, 10),
    }
    for lima in objects_of_type(session, Lima).values():
        lima.roi_counters.update(rois)


def mca_rois(session):
    rois = {"roi1": (500, 550), "roi2": (600, 650), "roi3": (700, 750)}
    for mca in objects_of_type(session, BaseMCA).values():
        for name, roi in rois.items():
            mca.rois.set(name, *roi)
