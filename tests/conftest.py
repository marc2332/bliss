# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import socket
import shutil
from collections import namedtuple
import atexit
import redis
import pytest
import gevent

from bliss.common import subprocess
from bliss.common import session as session_module
from bliss import setup_globals
from bliss.config import static
from bliss.config.conductor import client
from bliss.config.channels import clear_cache, Bus
from bliss.config.conductor.client import get_default_connection


BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BEACON = [sys.executable, "-m", "bliss.config.conductor.server"]
BEACON_DB_PATH = os.path.join(BLISS, "tests", "test_configuration")


def get_open_ports(n):
    sockets = [socket.socket() for _ in range(n)]
    try:
        for s in sockets:
            s.bind(("", 0))
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:
            s.close()


def wait_for(stream, target, data=b""):
    target = target.encode()
    while target not in data:
        char = stream.read(1)
        if not char:
            raise RuntimeError(
                "Target {!r} not found in the following stream:\n{}".format(
                    target, data.decode()
                )
            )
        data += char


@pytest.fixture
def clean_louie():
    import louie.dispatcher as disp

    disp.connections = {}
    disp.senders = {}
    disp.senders_back = {}
    disp.plugins = []
    yield disp
    assert disp.connections == {}
    assert disp.senders == {}
    assert disp.senders_back == {}
    assert disp.plugins == []
    disp.reset()


@pytest.fixture
def clean_gevent():
    import gc
    from gevent import Greenlet

    for ob in gc.get_objects():
        try:
            if not isinstance(ob, Greenlet):
                continue
        except ReferenceError:
            continue
        if ob.ready():
            continue
        ob.kill()

    d = {"end-check": True}
    yield d
    if not d.get("end-check"):
        return

    for ob in gc.get_objects():
        try:
            if not isinstance(ob, Greenlet):
                continue
        except ReferenceError:
            continue
        if not ob.ready():
            print(ob)  # Better printouts
        assert ob.ready()


@pytest.fixture
def clean_session():
    session_module.CURRENT_SESSION = None
    yield
    current_session = session_module.get_current()
    if current_session is not None:
        current_session.close()
    assert session_module.CURRENT_SESSION is None
    setup_globals.__dict__.clear()


@pytest.fixture(scope="session")
def config_app_port(ports):
    yield ports.cfgapp_port


@pytest.fixture(scope="session")
def beacon_directory(tmpdir_factory):
    tmpdir = str(tmpdir_factory.mktemp("beacon"))
    beacon_dir = os.path.join(tmpdir, "test_configuration")
    shutil.copytree(BEACON_DB_PATH, beacon_dir)
    yield beacon_dir


@pytest.fixture(scope="session")
def ports(beacon_directory):
    redis_uds = os.path.join(beacon_directory, "redis.sock")
    ports = namedtuple("Ports", "redis_port tango_port beacon_port cfgapp_port")(
        *get_open_ports(4)
    )
    args = [
        "--port=%d" % ports.beacon_port,
        "--redis_port=%d" % ports.redis_port,
        "--redis_socket=" + redis_uds,
        "--db_path=" + beacon_directory,
        "--posix_queue=0",
        "--tango_port=%d" % ports.tango_port,
        "--webapp_port=%d" % ports.cfgapp_port,
    ]
    proc = subprocess.Popen(BEACON + args, stderr=subprocess.PIPE)
    wait_for(proc.stderr, "database started on port")

    os.environ["TANGO_HOST"] = "localhost:%d" % ports.tango_port
    os.environ["BEACON_HOST"] = "localhost:%d" % ports.beacon_port
    try:
        yield ports
    finally:
        atexit._run_exitfuncs()
        proc.terminate()
        print(proc.stderr.read().decode(), file=sys.stderr)


@pytest.fixture
def beacon(ports):
    redis_db = redis.Redis(port=ports.redis_port)
    redis_db.flushall()
    static.CONFIG = None
    client._default_connection = None
    config = static.get_config()
    yield config
    config.close()
    client._default_connection = None
    static.CONFIG = None


@pytest.fixture
def beacon_host_port(ports):
    return "localhost", ports.beacon_port


@pytest.fixture
def redis_data_conn(beacon):
    cnx = get_default_connection()
    redis_conn = cnx.get_redis_connection(db=1)
    yield redis_conn


@pytest.fixture
def scan_tmpdir(tmpdir):
    yield tmpdir
    tmpdir.remove()


@pytest.fixture
def lima_simulator(ports, beacon):
    from Lima.Server.LimaCCDs import main
    from bliss.common.tango import DeviceProxy, DevFailed

    device_name = "id00/limaccds/simulator1"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    p = subprocess.Popen(["LimaCCDs", "simulator"])

    with gevent.Timeout(10, RuntimeError("Lima simulator is not running")):
        while True:
            try:
                dev_proxy = DeviceProxy(device_fqdn)
                dev_proxy.ping()
                dev_proxy.state()
            except DevFailed as e:
                gevent.sleep(0.1)
            else:
                break

    gevent.sleep(1)
    try:
        yield device_fqdn, dev_proxy
    finally:
        p.terminate()


@pytest.fixture
def bliss_tango_server(ports, beacon):
    from bliss.common.tango import DeviceProxy, DevFailed

    device_name = "id00/bliss/test"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    bliss_ds = [sys.executable, "-u", "-m", "bliss.tango.servers.bliss_ds"]
    p = subprocess.Popen(bliss_ds + ["test"], stdout=subprocess.PIPE)

    with gevent.Timeout(10, RuntimeError("Bliss tango server is not running")):
        wait_for(p.stdout, "Ready to accept request")

    dev_proxy = DeviceProxy(device_fqdn)

    yield device_fqdn, dev_proxy

    p.terminate()


@pytest.fixture
def dummy_tango_server(ports, beacon):
    from bliss.common.tango import DeviceProxy, DevFailed

    device_name = "id00/tango/dummy"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)
    dummy_ds = [
        sys.executable,
        "-u",
        os.path.join(os.path.dirname(__file__), "dummy_tg_server.py"),
    ]
    p = subprocess.Popen(dummy_ds + ["dummy"], stdout=subprocess.PIPE)

    with gevent.Timeout(10, RuntimeError("Bliss tango server is not running")):
        wait_for(p.stdout, "Ready to accept request")

    dev_proxy = DeviceProxy(device_fqdn)

    yield device_fqdn, dev_proxy

    p.terminate()


@pytest.fixture
def session(beacon):
    session = beacon.get("test_session")
    session.setup()
    yield session
    session.close()


def pytest_addoption(parser):
    parser.addoption("--pepu", help="pepu host name")
    parser.addoption("--ct2", help="ct2 address")
    parser.addoption("--axis-name", help="axis name")
    parser.addoption("--mythen", action="store", help="mythen host name")


@pytest.fixture
def alias_session(beacon, lima_simulator):
    from bliss.common.tango import DeviceProxy
    from bliss.controllers.lima.roi import Roi

    session = beacon.get("test_alias")
    env_dict = dict()
    session.setup(env_dict)

    ls = env_dict["lima_simulator"]
    rois = ls.roi_counters
    dev_name = lima_simulator[0].lower()
    roi_dev = DeviceProxy(dev_name.replace("limaccds", "roicounter"))
    r1 = Roi(0, 0, 100, 200)
    rois["r1"] = r1
    r2 = Roi(100, 100, 100, 200)
    rois["r2"] = r2
    r3 = Roi(200, 200, 200, 200)
    rois["r3"] = r3

    env_dict["ALIASES"].create_alias("myroi3", "lima_simulator.roi_counters.r3.sum")

    yield env_dict, session
    session.close()
