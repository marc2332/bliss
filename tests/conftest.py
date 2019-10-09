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
import gevent
import struct
import subprocess

import pytest
import redis

from bliss import global_map
from bliss.common.session import DefaultSession
from bliss.config import static
from bliss.config.conductor import client
from bliss.config.conductor import connection
from bliss.config.conductor.client import get_default_connection
from bliss.controllers.lima.roi import Roi
from bliss.controllers.wago.wago import ModulesConfig


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


def wait_for(stream, target):
    def do_wait_for(stream, target, data=b""):
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

    return do_wait_for(stream, target)


# the following is to share 'wait_for' function to all tests,
# since it is needed by some other tests (like Tango serial line,
# as it runs the Tango device server)
@pytest.fixture
def wait_for_fixture():
    return wait_for


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
    # assert main._GLOBAL_DICT['session'] is None
    yield
    global_map.clear()


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
    gevent.sleep(
        1
    )  # ugly synchronisation, would be better to use logging messages? Like 'post_init_cb()' (see databaseds.py in PyTango source code)

    os.environ["TANGO_HOST"] = "localhost:%d" % ports.tango_port
    os.environ["BEACON_HOST"] = "localhost:%d" % ports.beacon_port

    yield ports

    atexit._run_exitfuncs()
    proc.terminate()
    print(proc.stderr.read().decode(), file=sys.stderr)


@pytest.fixture
def beacon(ports):
    redis_db = redis.Redis(port=ports.redis_port)
    redis_db.flushall()
    static.CONFIG = None
    client._default_connection = connection.Connection("localhost", ports.beacon_port)
    config = static.get_config()
    yield config
    config.close()
    client._default_connection.close()


@pytest.fixture
def beacon_host_port(ports):
    return "localhost", ports.beacon_port


@pytest.fixture
def redis_conn(beacon):
    cnx = get_default_connection()
    redis_conn = cnx.get_redis_connection()
    yield redis_conn


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
    yield device_fqdn, dev_proxy
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
def wago_tango_server(ports, beacon):
    from bliss.tango.servers.wago_ds import main
    from bliss.common.tango import DeviceProxy, DevFailed

    device_name = "1/1/wagodummy"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    p = subprocess.Popen(["Wago", "wago_tg_server"])

    with gevent.Timeout(10, RuntimeError("WagoDS is not running")):
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

    yield device_fqdn, dev_proxy

    p.terminate()


@pytest.fixture
def tango_serial(ports, beacon):
    from bliss.common.tango import DeviceProxy, DevFailed

    device_name = "id00/tango/serial"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)
    serial_ds = [
        sys.executable,
        "-u",
        os.path.join(os.path.dirname(__file__), "serial_tg_server.py"),
    ]
    p = subprocess.Popen(serial_ds + ["serial"], stdout=subprocess.PIPE)

    with gevent.Timeout(10, RuntimeError("Serial tango server is not running")):
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


@pytest.fixture
def default_session(beacon):
    default_session = DefaultSession()
    default_session.setup()
    yield default_session
    default_session.close()


def pytest_addoption(parser):
    parser.addoption("--pepu", help="pepu host name")
    parser.addoption("--ct2", help="ct2 address")
    parser.addoption("--axis-name", help="axis name")
    parser.addoption("--mythen", action="store", help="mythen host name")
    parser.addoption(
        "--wago",
        help="connection information: tango_cpp_host:port,domani,wago_dns\nExample: --wago bibhelm:20000,ID31,wcid31c",
    )


@pytest.fixture
def alias_session(beacon, lima_simulator):
    session = beacon.get("test_alias")
    env_dict = dict()
    session.setup(env_dict)

    ls = env_dict["lima_simulator"]
    rois = ls.roi_counters
    r1 = Roi(0, 0, 100, 200)
    rois["r1"] = r1
    r2 = Roi(100, 100, 100, 200)
    rois["r2"] = r2
    r3 = Roi(200, 200, 200, 200)
    rois["r3"] = r3

    env_dict["ALIASES"].add("myroi", ls.counters.r1_sum)
    env_dict["ALIASES"].add("myroi3", ls.counters.r3_sum)

    yield session

    session.close()


@pytest.fixture
def wago_mockup(default_session):
    # do not use wago_mockup fixture together with default_session
    # because default_session already launches a wago_simulator and it will cause error on closing
    from tests.emulators.wago import WagoMockup

    config_tree = default_session.config.get_config("wago_simulator")
    wago = WagoMockup(config_tree)
    yield wago
    wago.close()
