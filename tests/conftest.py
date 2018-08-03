# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import time

import redis
import pytest
import gevent
import sys

from bliss.common import subprocess
from bliss.config import static
from bliss.config.conductor import client
from bliss.config.conductor import connection
from bliss.config.conductor.client import get_default_connection
from bliss.config.channels import clear_cache, Bus

REDIS_PORT = 7654
TANGO_PORT = 12345
BEACON_PORT = 7655
CFGAPP_PORT = 7656
BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BEACON = [sys.executable, '-m', 'bliss.config.conductor.server']
BEACON_DB_PATH = os.path.join(BLISS, 'tests', 'test_configuration')


@pytest.fixture
def clean_louie():
    import louie.dispatcher as disp

    assert disp.connections == {}
    assert disp.senders == {}
    assert disp.senders_back == {}
    assert disp.plugins == []
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
        if not isinstance(ob, Greenlet):
            continue
        if ob.ready():
            continue
        ob.kill()

    yield

    for ob in gc.get_objects():
        if not isinstance(ob, Greenlet):
            continue
        if not ob.ready():
            print(ob)  # Better printouts
        assert ob.ready()


@pytest.fixture(scope="session")
def config_app_port():
    yield CFGAPP_PORT


@pytest.fixture(scope="session")
def _beacon():
    args = [
        '--port=%d' % BEACON_PORT,
        '--redis_port=%d' % REDIS_PORT,
        '--redis_socket=/tmp/redis_test.sock',
        '--db_path=' + BEACON_DB_PATH,
        '--posix_queue=0',
        '--tango_port=%d' % TANGO_PORT,
        '--webapp_port=%d' % CFGAPP_PORT]
    proc = subprocess.Popen(BEACON + args)
    time.sleep(0.5)  # wait for beacon to be really started
    redis_db = redis.Redis(port=REDIS_PORT)
    redis_db.flushall()
    beacon_connection = connection.Connection("localhost", BEACON_PORT)
    client._default_connection = beacon_connection
    cfg = static.get_config()
    os.environ["TANGO_HOST"] = "localhost:%d" % TANGO_PORT
    os.environ["BEACON_HOST"] = "localhost:%d" % BEACON_PORT
    try:
        yield (cfg, redis_db)
    finally:
        proc.terminate()


@pytest.fixture
def beacon(_beacon):
    cfg, redis_db = _beacon
    yield cfg
    clear_cache()
    Bus.clear_cache()
    redis_db.flushall()
    cfg._clear_instances()


@pytest.fixture
def beacon_host_port():
    return "localhost", BEACON_PORT


@pytest.fixture
def redis_data_conn():
    cnx = get_default_connection()
    redis_conn = cnx.get_redis_connection(db=1)
    yield redis_conn


@pytest.fixture
def scan_tmpdir(tmpdir):
    yield tmpdir
    tmpdir.remove()


@pytest.fixture
def lima_simulator(beacon):
    from Lima.Server.LimaCCDs import main
    from tango import DeviceProxy, DevFailed

    device_name = "id00/limaccds/simulator1"
    device_fqdn = "tango://localhost:12345/%s" % device_name

    p = subprocess.Popen(['LimaCCDs', 'simulator'])

    with gevent.Timeout(3, RuntimeError("Lima simulator is not running")):
        while True:
            try:
                dev_proxy = DeviceProxy(device_fqdn)
                dev_proxy.ping()
                dev_proxy.state()
            except DevFailed as e:
                gevent.sleep(0.5)
            else:
                break

    gevent.sleep(0.5)
    try:
        yield device_fqdn, dev_proxy
    finally:
        p.terminate()


@pytest.fixture
def bliss_tango_server(beacon):
    from tango import DeviceProxy, DevFailed

    device_name = "id00/bliss/test"
    device_fqdn = "tango://localhost:12345/%s" % device_name

    bliss_ds = [sys.executable, '-m', 'bliss.tango.servers.bliss_ds']
    p = subprocess.Popen(bliss_ds+["test"])

    with gevent.Timeout(3, RuntimeError("Bliss tango server is not running")):
        while True:
            try:
                dev_proxy = DeviceProxy(device_fqdn)
                dev_proxy.ping()
                dev_proxy.state()
            except DevFailed as e:
                gevent.sleep(0.5)
            else:
                break

    # Might help, for other devices...
    gevent.sleep(1)
    yield device_fqdn, dev_proxy
    p.terminate()


@pytest.fixture
def session(beacon):
    session = beacon.get("test_session")
    session.setup()
    yield session
    session.close()
