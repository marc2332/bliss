# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import subprocess
import os
import time

from bliss.config import static
from bliss.config.conductor import client
from bliss.config.conductor import connection
import redis

BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BEACON = ['python', '-m', 'bliss.config.conductor.server']
BEACON_DB_PATH = os.path.join(BLISS, 'tests', 'test_configuration')
BEACON_PORT = 7655


@pytest.fixture(scope="session")
def beacon():
    args = [
        '--port=%d' % BEACON_PORT,
        '--redis_port=7654',
        '--redis_socket=/tmp/redis_test.sock',
        '--db_path='+BEACON_DB_PATH,
        '--posix_queue=0']
    p = subprocess.Popen(BEACON + args)
    time.sleep(0.5)  # wait for beacon to be really started
    redis_db = redis.Redis(port=7654)
    redis_db.flushdb()
    beacon_connection = connection.Connection("localhost", BEACON_PORT)
    client._default_connection = beacon_connection
    cfg = static.get_config()
    yield cfg
    p.terminate()
