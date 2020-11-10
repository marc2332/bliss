# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import shutil
from collections import namedtuple
import atexit
import gc
import gevent
from gevent import Greenlet
import subprocess
import signal
import logging
import json
import pytest
import redis
import collections.abc
import numpy
from random import randint
from contextlib import contextmanager
import weakref
from pprint import pprint

from bliss import global_map, global_log
from bliss.common.session import DefaultSession
from bliss.common.utils import get_open_ports
from bliss.common import logtools
from bliss.config import static
from bliss.config import settings_cache
from bliss.config.conductor import client
from bliss.config.conductor import connection
from bliss.config.conductor.client import get_default_connection
from bliss.controllers.lima.roi import Roi
from bliss.controllers.wago.wago import ModulesConfig
from bliss.controllers.wago.emulator import WagoEmulator
from bliss.controllers import simulation_diode
from bliss.controllers import tango_attr_as_counter
from bliss.common import plot
from bliss.common.tango import Database, DeviceProxy, DevFailed, ApiUtil, DevState
from bliss.common.utils import grouped
from bliss.tango.clients.utils import wait_tango_device, wait_tango_db
from bliss import logging_startup
from bliss.scanning import scan_meta
import socket

BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BEACON = [sys.executable, "-m", "bliss.config.conductor.server"]
BEACON_DB_PATH = os.path.join(BLISS, "tests", "test_configuration")
IMAGES_PATH = os.path.join(BLISS, "tests", "images")

SERVICE = [sys.executable, "-m", "bliss.comm.service"]


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


def wait_terminate(process):
    cmd = repr(" ".join(process.args))
    if process.poll() is not None:
        eprint(f"Process {cmd} already terminated with code {process.returncode}")
        return
    process.terminate()
    try:
        with gevent.Timeout(10):
            process.wait()
    except gevent.Timeout:
        eprint(f"Process {cmd} doesn't finish: try to kill it ...")
        process.kill()
        with gevent.Timeout(10):
            process.wait()


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


class GreenletsContext:
    """
    This context ensure that every greenlet created during its execution
    are properly released.

    If a greenlet is still alive at the exit, a warning is displayed,
    and it tries to kill it.

    It is not concurrency safe. The global context is used to
    check available greenlets.
    """

    def __init__(self):
        self.greenlets_before = weakref.WeakSet()
        self.all_greenlets_ready = None

    def __enter__(self):
        self.greenlets_before.clear()
        self.all_greenlets_ready = None

        for ob in gc.get_objects():
            try:
                if not isinstance(ob, Greenlet):
                    continue
            except ReferenceError:
                continue
            self.greenlets_before.add(ob)

    def __exit__(self, exc_type, exc_val, exc_tb):
        greenlets = []
        for ob in gc.get_objects():
            try:
                if not isinstance(ob, Greenlet):
                    continue
            except ReferenceError:
                continue
            if ob in self.greenlets_before:
                continue

            if not ob.ready():
                eprint(f"Dangling greenlet (teardown): {ob}")
            greenlets.append(ob)

        self.greenlets_before.clear()
        self.all_greenlets_ready = all(gr.ready() for gr in greenlets)
        with gevent.Timeout(10, RuntimeError("Dangling greenlets cannot be killed")):
            gevent.killall(greenlets)


@pytest.fixture
def clean_gevent():
    """
    Context manager to check that greenlets are properly released during a test.

    It is not concurrency safe. The global context is used to
    check available greenlets.

    If the fixture is used as the last argument if will only test the greenlets
    creating during the test.

    .. code-block:: python

        def test_a(fixture_a, fixture_b, clean_gevent):
            ...

    If the fixture is used as the first argument if will also test greenlets
    created by sub fixtures.

    .. code-block:: python

        def test_b(clean_gevent, fixture_a, fixture_b):
            ...
    """
    d = {"end-check": True}
    context = GreenletsContext()
    with context:
        yield d
    end_check = d.get("end-check")
    if end_check:
        assert context.all_greenlets_ready


@pytest.fixture
def clean_globals():
    yield
    global_log.clear()
    global_map.clear()
    # reset module-level globals
    simulation_diode.DEFAULT_CONTROLLER = None
    simulation_diode.DEFAULT_INTEGRATING_CONTROLLER = None
    scan_meta.USER_SCAN_META = None
    logtools.userlogger.reset()
    tango_attr_as_counter._TangoCounterControllerDict = weakref.WeakValueDictionary()


@pytest.fixture
def clean_tango():
    # close file descriptors left open by Tango (see tango-controls/pytango/issues/324)
    try:
        ApiUtil.cleanup()
    except RuntimeError:
        # no Tango ?
        pass


@pytest.fixture(scope="session")
def config_app_port(ports):
    yield ports.cfgapp_port


@pytest.fixture(scope="session")
def beacon_tmpdir(tmpdir_factory):
    tmpdir = str(tmpdir_factory.mktemp("beacon"))
    yield tmpdir


@pytest.fixture(scope="session")
def beacon_directory(beacon_tmpdir):
    beacon_dir = os.path.join(beacon_tmpdir, "test_configuration")
    shutil.copytree(BEACON_DB_PATH, beacon_dir)
    yield beacon_dir


@pytest.fixture(scope="session")
def log_directory(beacon_tmpdir):
    log_dir = os.path.join(beacon_tmpdir, "log")
    os.mkdir(log_dir)
    yield log_dir


@pytest.fixture(scope="session")
def images_directory(tmpdir_factory):
    images_dir = os.path.join(str(tmpdir_factory.getbasetemp()), "images")
    shutil.copytree(IMAGES_PATH, images_dir)
    yield images_dir


@pytest.fixture(scope="session")
def ports(beacon_directory, log_directory):
    redis_uds = os.path.join(beacon_directory, "redis.sock")
    redis_data_uds = os.path.join(beacon_directory, "redis_data.sock")
    ports = namedtuple(
        "Ports",
        "redis_port redis_data_port tango_port beacon_port cfgapp_port logserver_port",
    )(*get_open_ports(6))
    args = [
        "--port=%d" % ports.beacon_port,
        "--redis_port=%d" % ports.redis_port,
        "--redis_socket=" + redis_uds,
        "--redis-data-port=%d" % ports.redis_data_port,
        "--redis-data-socket=" + redis_data_uds,
        "--db_path=%s" % beacon_directory,
        "--tango_port=%d" % ports.tango_port,
        "--webapp_port=%d" % ports.cfgapp_port,
        "--log_server_port=%d" % ports.logserver_port,
        "--log_output_folder=%s" % log_directory,
    ]
    proc = subprocess.Popen(BEACON + args)
    wait_ports(ports)

    # disable .rdb files saving (redis persistence)
    r = redis.Redis(host="localhost", port=ports.redis_port)
    r.config_set("SAVE", "")
    del r

    os.environ["TANGO_HOST"] = "localhost:%d" % ports.tango_port
    os.environ["BEACON_HOST"] = "localhost:%d" % ports.beacon_port

    yield ports

    atexit._run_exitfuncs()
    wait_terminate(proc)


def wait_ports(ports, timeout=10):
    with gevent.Timeout(timeout):
        wait_tcp_online("localhost", ports.beacon_port)
        wait_tango_db(port=ports.tango_port, db=2)


@pytest.fixture
def beacon(ports):
    redis_db = redis.Redis(port=ports.redis_port)
    redis_db.flushall()
    redis_data_db = redis.Redis(port=ports.redis_data_port)
    redis_data_db.flushall()
    static.Config.instance = None
    client._default_connection = connection.Connection("localhost", ports.beacon_port)
    config = static.get_config()
    yield config
    config.close()
    client._default_connection.close()
    # Ensure no connections are created due to garbage collection:
    client._default_connection = None
    settings_cache.close_all_client_cache()


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


@contextmanager
def start_tango_server(*cmdline_args, **kwargs):
    device_fqdn = kwargs["device_fqdn"]
    exception = None
    for i in range(3):
        p = subprocess.Popen(cmdline_args)
        try:
            dev_proxy = wait_tango_device(**kwargs)
        except Exception as e:
            exception = e
            wait_terminate(p)
        else:
            break
    else:
        raise RuntimeError(f"could not start {device_fqdn}") from exception

    try:
        yield dev_proxy
    finally:
        wait_terminate(p)


@contextmanager
def lima_simulator_context(personal_name, device_name):
    fqdn_prefix = f"tango://{os.environ['TANGO_HOST']}"
    device_fqdn = f"{fqdn_prefix}/{device_name}"
    admin_device_fqdn = f"{fqdn_prefix}/dserver/LimaCCDs/{personal_name}"

    with start_tango_server(
        "LimaCCDs",
        personal_name,
        # "-v4",               # to enable debug
        device_fqdn=device_fqdn,
        admin_device_fqdn=admin_device_fqdn,
        state=None,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def lima_simulator(ports):
    with lima_simulator_context("simulator", "id00/limaccds/simulator1") as fqdn_proxy:
        yield fqdn_proxy


@pytest.fixture
def lima_simulator2(ports):
    with lima_simulator_context("simulator2", "id00/limaccds/simulator2") as fqdn_proxy:
        yield fqdn_proxy


@pytest.fixture
def bliss_tango_server(ports, beacon):
    device_name = "id00/bliss/test"
    fqdn_prefix = f"tango://{os.environ['TANGO_HOST']}"
    device_fqdn = f"{fqdn_prefix}/{device_name}"
    admin_device_fqdn = f"{fqdn_prefix}/dserver/bliss/test"

    with start_tango_server(
        sys.executable,
        "-u",
        "-m",
        "bliss.tango.servers.bliss_ds",
        "test",
        device_fqdn=device_fqdn,
        admin_device_fqdn=admin_device_fqdn,
        state=DevState.STANDBY,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def dummy_tango_server(ports, beacon):

    device_name = "id00/tango/dummy"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    with start_tango_server(
        sys.executable,
        "-u",
        os.path.join(os.path.dirname(__file__), "dummy_tg_server.py"),
        "dummy",
        device_fqdn=device_fqdn,
        state=DevState.CLOSE,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def wago_tango_server(ports, default_session, wago_emulator):
    device_name = "1/1/wagodummy"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    # patching the property Iphost of wago tango device to connect to the mockup
    wago_ds = DeviceProxy(device_fqdn)
    wago_ds.put_property({"Iphost": f"{wago_emulator.host}:{wago_emulator.port}"})

    with start_tango_server(
        "Wago", "wago_tg_server", device_fqdn=device_fqdn
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def machinfo_tango_server(ports, beacon):
    device_name = "id00/tango/machinfo"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    with start_tango_server(
        sys.executable,
        "-u",
        os.path.join(os.path.dirname(__file__), "machinfo_tg_server.py"),
        "machinfo",
        device_fqdn=device_fqdn,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def session(beacon, scan_tmpdir):
    session = beacon.get("test_session")
    session.setup()
    session.scan_saving.base_path = str(scan_tmpdir)
    yield session
    session.close()


@pytest.fixture
def default_session(beacon, scan_tmpdir):
    default_session = DefaultSession()
    default_session.setup()
    default_session.scan_saving.base_path = str(scan_tmpdir)
    yield default_session
    default_session.close()


def pytest_addoption(parser):
    """
    Add pytest options
    """
    parser.addoption("--runwritertests", action="store_true", help="run external tests")
    parser.addoption("--pepu", help="pepu host name")
    parser.addoption("--ct2", help="ct2 address")
    parser.addoption("--axis-name", help="axis name")
    parser.addoption("--mythen", action="store", help="mythen host name")
    parser.addoption(
        "--wago",
        help="connection information: tango_cpp_host:port,domani,wago_dns\nExample: --wago bibhelm:20000,ID31,wcid31c",
    )


def pytest_configure(config):
    """
    Modify pytest.ini
    """
    # Define new test markers which allow to selecting specific tests
    # from the CLI, for example "pytest -m nexuswriter"
    config.addinivalue_line(
        "markers", "writer: mark as a writer test (skipped default)"
    )


def pytest_collection_modifyitems(config, items):
    """
    Add test markers dynamically based on pytest options
    (see `pytest_addoption`)
    """
    mark_dir_tests(items, "nexus_writer", pytest.mark.writer)
    skip_tests(config, items)


def mark_dir_tests(items, dirname, marker):
    """
    Mark tests based on directory
    """
    for item in items:
        if dirname == os.path.split(os.path.dirname(item.fspath))[-1]:
            item.add_marker(marker)


def skip_tests(config, items):
    """
    Skip marked tests when not enabled (see `pytest_addoption`)
    """
    skip_markers = ["writer"]
    skip_markers = [
        m for m in skip_markers if not config.getoption("--run{}tests".format(m))
    ]
    if not skip_markers:
        # Do not skip any tests
        return
    skip_markers = {
        m: pytest.mark.skip(reason="need --run{}tests option to run".format(m))
        for m in skip_markers
    }
    for item in items:
        for m, marker in skip_markers.items():
            if m in item.keywords:
                # Mark test as skipped
                item.add_marker(marker)


@pytest.fixture
def alias_session(beacon, lima_simulator, scan_tmpdir):
    session = beacon.get("test_alias")
    env_dict = dict()
    session.setup(env_dict)
    session.scan_saving.base_path = str(scan_tmpdir)

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
def wago_emulator(beacon):
    config_tree = beacon.get_config("wago_simulator")
    modules_config = ModulesConfig.from_config_tree(config_tree)
    wago = WagoEmulator(modules_config)

    yield wago

    wago.close()


@pytest.fixture(scope="session")
def xvfb():
    xvfb = shutil.which("Xvfb")
    # Xvfb not found
    if xvfb is None:
        yield
        return
    # Control DISPLAY variable
    try:
        display = os.environ.get("DISPLAY")
        new_display = ":{}".format(randint(100, 1000000000))
        os.environ["DISPLAY"] = new_display
        # Control xvbf process
        try:
            p = subprocess.Popen([xvfb, "-screen", "0", "1024x768x24", new_display])
            yield p.pid
        # Teardown process
        finally:
            p.kill()
            p.wait(1.)
    # Restore DISPLAY variable
    finally:
        if display:
            os.environ["DISPLAY"] = display


@contextmanager
def flint_context(with_flint=True):
    if with_flint:
        flint = plot.get_flint()
    else:
        flint = plot.get_flint(creation_allowed=False)
        if flint is not None:
            flint.close()
            flint = None  # Break the reference to the proxy
            plot.reset_flint()
    yield
    flint = plot.get_flint(creation_allowed=False)
    if flint is not None:
        flint.close()
        flint = None  # Break the reference to the proxy
    plot.reset_flint()


@pytest.fixture
def flint_session(xvfb, beacon, scan_tmpdir):
    session = beacon.get("flint")
    session.setup()
    session.scan_saving.base_path = str(scan_tmpdir)
    with flint_context():
        yield session
    session.close()


@pytest.fixture
def test_session_with_flint(xvfb, session):
    with flint_context():
        yield session


@pytest.fixture
def test_session_without_flint(xvfb, session):
    """This session have to start without flint, but can finish with"""
    with flint_context(False):
        yield session


@pytest.fixture
def log_context():
    """
    Create a new log instance
    """
    # Save the logging context
    old_handlers = list(logging.getLogger().handlers)
    old_logger_dict = dict(logging.getLogger().manager.loggerDict)

    logging_startup()

    yield

    # Restore the logging context
    logging.shutdown()
    logging.setLoggerClass(logging.Logger)
    logging.getLogger().handlers.clear()  # deletes all handlers
    logging.getLogger().handlers.extend(old_handlers)
    logging.getLogger().manager.loggerDict.clear()  # deletes all loggers
    logging.getLogger().manager.loggerDict.update(old_logger_dict)


def deep_compare(d, u):
    """using logic of deep update used here to compare two dicts 
    """
    try:
        stack = [(d, u)]
        while stack:
            d, u = stack.pop(0)
            assert len(d) == len(u)

            for k, v in u.items():
                assert k in d
                if not isinstance(v, collections.abc.Mapping):
                    if isinstance(v, numpy.ndarray) and v.size > 1:
                        assert d[k].shape == v.shape
                        d[k].dtype == v.dtype
                        if d[k].dtype != numpy.object:
                            assert all(
                                numpy.isnan(d[k].flatten()) == numpy.isnan(v.flatten())
                            )
                            mask = numpy.logical_not(numpy.isnan(v.flatten()))
                            assert all((d[k].flatten() == v.flatten())[mask])
                        else:
                            assert all(d[k].flatten() == v.flatten())
                    else:
                        assert d[k] == v
                else:
                    stack.append((d[k], v))
    except AssertionError:
        pprint(d)
        pprint(u)
        raise


@pytest.fixture
def metamgr_without_backend(ports, beacon):
    device_name = "id00/metadata/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    db = Database()
    db.put_class_property("MetadataManager", {"jolokiaPort": 0})
    db.put_class_property("MetadataManager", {"queueURLs": [""]})
    db.put_class_property("MetadataManager", {"queueName": ""})
    db.put_class_property("MetadataManager", {"icatplus_server": ""})

    with start_tango_server(
        sys.executable,
        "-u",
        "-m",
        "metadata_manager.MetadataManager",
        "test",
        "-v2",
        device_fqdn=device_fqdn,
        state=DevState.OFF,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def metamgr_with_backend(
    ports, beacon, jolokia_server, stomp_server, icat_logbook_server
):
    device_name = "id00/metadata/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    db = Database()
    _, port = jolokia_server
    db.put_class_property("MetadataManager", {"jolokiaPort": port})
    host, port = stomp_server
    db.put_class_property("MetadataManager", {"queueURLs": [f"{host}:{port}"]})
    db.put_class_property("MetadataManager", {"queueName": "/queue/icatIngest"})
    db.put_class_property(
        "MetadataManager", {"API_KEY": "elogbook-0000-000-0000-0000-0000"}
    )
    port, _ = icat_logbook_server
    db.put_class_property(
        "MetadataManager", {"icatplus_server": f"http://localhost:{port}"}
    )

    with start_tango_server(
        sys.executable,
        "-u",
        "-m",
        "metadata_manager.MetadataManager",
        "test",
        "-v2",
        device_fqdn=device_fqdn,
        state=DevState.OFF,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def metaexp_without_backend(ports, beacon):
    device_name = "id00/metaexp/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    db = Database()
    db.put_class_property("MetaExperiment", {"jolokiaPort": 0})
    db.put_class_property("MetaExperiment", {"queueURLs": [""]})
    db.put_class_property("MetaExperiment", {"queueName": ""})
    db.put_class_property("MetaExperiment", {"icatplus_server": ""})

    with start_tango_server(
        sys.executable,
        "-u",
        "-m",
        "metadata_manager.MetaExperiment",
        "test",
        "-v2",
        device_fqdn=device_fqdn,
        state=DevState.ON,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def metaexp_with_backend(
    ports, beacon, jolokia_server, stomp_server, icat_logbook_server
):
    device_name = "id00/metaexp/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    db = Database()
    _, port = jolokia_server
    db.put_class_property("MetaExperiment", {"jolokiaPort": port})
    host, port = stomp_server
    db.put_class_property("MetaExperiment", {"queueURLs": [f"{host}:{port}"]})
    db.put_class_property("MetaExperiment", {"queueName": "/queue/icatIngest"})
    db.put_class_property(
        "MetaExperiment", {"API_KEY": "elogbook-0000-000-0000-0000-0000"}
    )

    with start_tango_server(
        sys.executable,
        "-u",
        "-m",
        "metadata_manager.MetaExperiment",
        "test",
        "-v2",
        device_fqdn=device_fqdn,
        state=DevState.ON,
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


def wait_tcp_online(host, port, timeout=10):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with gevent.Timeout(timeout):
            while True:
                try:
                    sock.connect((host, port))
                    break
                except ConnectionError:
                    pass
                gevent.sleep(0.1)
    finally:
        sock.close()


@contextmanager
def tcp_message_server(data_parser=None):
    """Start a TCP server and yield a queue of events.
    Data packages are separated by newline characters.
    Supported package encodings are UTF8 (default) and json.
    """
    # Create TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port = get_open_ports(1)[0]
    sock.bind(("localhost", port))
    sock.listen()

    # Listen to this TCP socket
    messages = gevent.queue.Queue()

    def listener():
        buffer = b""
        conn, addr = sock.accept()
        while True:
            buffer += conn.recv(16384)
            if buffer:
                out, sep, buffer = buffer.rpartition(b"\n")
                if sep:
                    for bdata in out.split(b"\n"):
                        if data_parser == "json":
                            messages.put(json.loads(bdata))
                        else:
                            messages.put(bdata.decode())
            gevent.sleep(0.1)

    glistener = gevent.spawn(listener)
    try:
        yield port, messages
    finally:
        messages.put(StopIteration)
        for msg in messages:
            eprint(f"Unvalidated message: {msg}")
        with gevent.Timeout(10):
            sock.close()
            glistener.kill()


@pytest.fixture
def jolokia_server():
    """One of the ICAT backends
    """
    port = get_open_ports(1)[0]
    path = os.path.dirname(__file__)
    script_path = os.path.join(path, "utils", "jolokia_server.py")
    p = subprocess.Popen([sys.executable, "-u", script_path, f"--port={port}"])
    wait_tcp_online("localhost", port)
    try:
        yield ("localhost", port)
    finally:
        wait_terminate(p)


@pytest.fixture
def userlogger_enabled():
    logtools.userlogger.enable()
    try:
        yield
    finally:
        logtools.userlogger.disable()


@pytest.fixture
def elogbook_enabled():
    logtools.elogbook.enable()
    try:
        yield
    finally:
        logtools.elogbook.disable()


@pytest.fixture
def log_shell_mode(userlogger_enabled, elogbook_enabled):
    pass


@pytest.fixture
def icat_logbook_server():
    """ICAT backend for the e-logbook
    """
    with tcp_message_server("json") as (port_out, messages):
        port = get_open_ports(1)[0]
        path = os.path.dirname(__file__)
        script_path = os.path.join(path, "utils", "icatplus_server.py")
        p = subprocess.Popen(
            [
                sys.executable,
                "-u",
                script_path,
                f"--port={port}",
                f"--port_out={port_out}",
            ]
        )
        wait_tcp_online("localhost", port)
        try:
            assert messages.get(timeout=10) == {"STATUS": "LISTENING"}
            yield port, messages
        finally:
            wait_terminate(p)


@pytest.fixture
def icat_logbook_subscriber(elogbook_enabled, icat_logbook_server):
    _, messages = icat_logbook_server
    try:
        yield messages
        assert len(messages) == 0, "not all messages have been validated"
    finally:
        messages.put(StopIteration)
        for msg in messages:
            print(f"\nUnvalidated message: {msg}")


@pytest.fixture
def stomp_server():
    """One of the ICAT backends
    """
    port = get_open_ports(1)[0]
    # Add arguments ["--debug", "TEXT"] for debugging
    proc = subprocess.Popen(["coilmq", "-b", "0.0.0.0", "-p", str(port)])
    wait_tcp_online("localhost", port)
    try:
        yield ("localhost", port)
    finally:
        wait_terminate(proc)


@pytest.fixture
def icat_subscriber(stomp_server):
    with tcp_message_server() as (port_out, messages):
        path = os.path.dirname(__file__)
        script_path = os.path.join(path, "utils", "stomp_subscriber.py")
        host, port = stomp_server
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                script_path,
                f"--host={host}",
                f"--port={port}",
                f"--port_out={port_out}",
                "--queue=/queue/icatIngest",
            ]
        )

        try:
            assert messages.get(timeout=10) == "LISTENING"
            yield messages
        finally:
            wait_terminate(proc)


@pytest.fixture
def icat_publisher(stomp_server):
    # Create TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_in = get_open_ports(1)[0]
    sock.bind(("localhost", port_in))
    sock.listen()

    # Redirect messages from TCP socket to STOMP server
    path = os.path.dirname(__file__)
    script_path = os.path.join(path, "utils", "stomp_publisher.py")
    host, port = stomp_server
    proc = subprocess.Popen(
        [
            sys.executable,
            "-u",
            script_path,
            f"--host={host}",
            f"--port={port}",
            f"--port_in={port_in}",
            "--queue=/queue/icatIngest",
        ]
    )
    try:
        conn, addr = sock.accept()
        with conn:
            yield conn
    finally:
        sock.close()
        wait_terminate(proc)


@pytest.fixture
def nexus_writer_service(ports):
    device_name = "id00/bliss_nxwriter/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    with start_tango_server(
        "NexusWriterService", "testwriters", "--log", "info", device_fqdn=device_fqdn
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def sim_ct_gauss_service(beacon):
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        SERVICE + ["sim_ct_gauss_service"], stdout=subprocess.PIPE, env=env
    )
    wait_for(proc.stdout, "Starting service sim_ct_gauss_service")
    gevent.sleep(0.5)
    proc.stdout.close()
    sim = beacon.get("sim_ct_gauss_service")
    yield sim
    sim.close()
    wait_terminate(proc)
