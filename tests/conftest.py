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
import gevent
import subprocess
import signal
import logging
import pytest
import redis
import collections.abc
import numpy
from random import randint
from contextlib import contextmanager
import redis
import weakref
from pprint import pprint

from bliss import global_map, global_log
from bliss.common.session import DefaultSession
from bliss.common.utils import get_open_ports
from bliss.common.logtools import logbook_printer
from bliss.config import static
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
from bliss import logging_startup
from bliss.scanning import scan_meta


BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BEACON = [sys.executable, "-m", "bliss.config.conductor.server"]
BEACON_DB_PATH = os.path.join(BLISS, "tests", "test_configuration")


def wait_terminate(process):
    process.terminate()
    try:
        with gevent.Timeout(10):
            process.wait()
    except gevent.Timeout:
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

    end_check = d.get("end-check")

    greenlets = []
    for ob in gc.get_objects():
        try:
            if not isinstance(ob, Greenlet):
                continue
        except ReferenceError:
            continue
        if end_check and not ob.ready():
            print(ob)  # Better printouts
        greenlets.append(ob)
    all_ready = all(gr.ready() for gr in greenlets)
    gevent.killall(greenlets)
    del greenlets
    if end_check:
        assert all_ready


@pytest.fixture
def clean_globals():
    yield
    global_log.clear()
    global_map.clear()
    # reset module-level globals
    simulation_diode.DEFAULT_CONTROLLER = None
    simulation_diode.DEFAULT_INTEGRATING_CONTROLLER = None
    scan_meta.USER_SCAN_META = None
    logbook_printer.disabled.clear()
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
        "--tango_port=%d" % ports.tango_port,
        "--webapp_port=%d" % ports.cfgapp_port,
    ]
    proc = subprocess.Popen(BEACON + args, stderr=subprocess.PIPE)
    with gevent.Timeout(10):
        wait_for(proc.stderr, "Tango DB started")
    proc.stderr.close()

    # disable .rdb files saving (redis persistence)
    r = redis.Redis(host="localhost", port=ports.redis_port)
    r.config_set("SAVE", "")
    del r

    os.environ["TANGO_HOST"] = "localhost:%d" % ports.tango_port
    os.environ["BEACON_HOST"] = "localhost:%d" % ports.beacon_port

    yield ports

    atexit._run_exitfuncs()
    wait_terminate(proc)


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


def wait_tango_device(
    device_fqdn=None, admin=None, state=DevState.ON, timeout=10, timeout_msg=None
):
    msg = timeout_msg if timeout_msg is not None else f"{device_fqdn} is not running"
    with gevent.Timeout(timeout, RuntimeError(msg)):
        while True:
            if admin:
                dev_proxy = DeviceProxy(admin)
            else:
                dev_proxy = DeviceProxy(device_fqdn)
            try:
                dev_proxy.ping()
            except DevFailed as e:
                gevent.sleep(1)
            else:
                break

        dev_proxy = DeviceProxy(device_fqdn)
        if state is not None:
            while dev_proxy.state() != state:
                gevent.sleep(0.1)

    return dev_proxy


@contextmanager
def start_tango_server(*cmdline_args, **kwargs):
    device_fqdn = kwargs["device_fqdn"]

    for i in range(3):
        p = subprocess.Popen(cmdline_args)

        try:
            dev_proxy = wait_tango_device(**kwargs)
        except BaseException:
            wait_terminate(p)

            continue
        else:
            break
    else:
        raise RuntimeError(f"could not start {device_fqdn}")

    try:
        yield dev_proxy
    finally:
        wait_terminate(p)


@contextmanager
def lima_simulator_context(personal_name, device_name):
    db = Database()
    fqdn_prefix = f"tango://{os.environ['TANGO_HOST']}"
    device_fqdn = f"{fqdn_prefix}/{device_name}"
    admin_device_fqdn = f"{fqdn_prefix}/dserver/LimaCCDs/{personal_name}"

    with start_tango_server(
        "LimaCCDs",
        personal_name,
        device_fqdn=device_fqdn,
        admin=admin_device_fqdn,
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
    db = Database()

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
        admin=admin_device_fqdn,
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
            flint.close_application()
            flint = None  # Break the reference to the proxy
            plot.reset_flint()
    yield
    flint = plot.get_flint(creation_allowed=False)
    if flint is not None:
        flint.close_application()
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
def metadata_manager_tango_server(ports):
    device_name = "id00/metadata/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    with start_tango_server(
        "MetadataManager", "test", "-v2", device_fqdn=device_fqdn, state=DevState.OFF
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def metadata_experiment_tango_server(ports):
    device_name = "id00/metaexp/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    with start_tango_server(
        "MetaExperiment", "test", "-v2", device_fqdn=device_fqdn, state=DevState.ON
    ) as dev_proxy:
        yield device_fqdn, dev_proxy


@pytest.fixture
def nexus_writer_service(ports):
    device_name = "id00/bliss_nxwriter/test_session"
    device_fqdn = "tango://localhost:{}/{}".format(ports.tango_port, device_name)

    with start_tango_server(
        "NexusWriterService", "testwriters", "--log", "info", device_fqdn=device_fqdn
    ) as dev_proxy:
        yield device_fqdn, dev_proxy
