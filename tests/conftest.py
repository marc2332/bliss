# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import time
import subprocess
import multiprocessing

import redis
import pytest
import gevent
import sys

from bliss.config import static
from bliss.config.conductor import client
from bliss.config.conductor import connection
from bliss.config.conductor.client import get_default_connection

BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BEACON = [sys.executable, '-m', 'bliss.config.conductor.server']
BEACON_DB_PATH = os.path.join(BLISS, 'tests', 'test_configuration')
BEACON_PORT = 7655


@pytest.fixture(scope="session")
def beacon():
    args = [
        '--port=%d' % BEACON_PORT,
        '--redis_port=7654',
        '--redis_socket=/tmp/redis_test.sock',
        '--db_path=' + BEACON_DB_PATH,
        '--posix_queue=0',
        '--tango_port=12345']
    proc = subprocess.Popen(BEACON + args)
    time.sleep(0.5)  # wait for beacon to be really started
    redis_db = redis.Redis(port=7654)
    redis_db.flushall()
    beacon_connection = connection.Connection("localhost", BEACON_PORT)
    client._default_connection = beacon_connection
    cfg = static.get_config()
    os.environ["TANGO_HOST"] = "localhost:12345"
    yield cfg
    proc.terminate()


@pytest.fixture
def redis_data_conn():
    cnx = get_default_connection()
    redis_conn = cnx.get_redis_connection(db=1)
    yield redis_conn


@pytest.fixture
def scan_tmpdir(tmpdir):
    yield tmpdir
    tmpdir.remove()


@pytest.fixture(scope="session")
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

    yield device_fqdn, dev_proxy
    p.terminate()


@pytest.fixture(scope="session")
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
