# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import subprocess
import sys
import os
import time

BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BEACON_PATH = os.path.join(BLISS, 'bin')
BEACON = os.path.join(BEACON_PATH, "beacon-server")
BEACON_DB_PATH = os.path.join(BLISS, 'tests', 'test_configuration')
BEACON_PORT = 7655

from bliss.config import static
from bliss.config.conductor import client
from bliss.config.conductor import connection

os.environ["PYTHONPATH"] = BLISS

@pytest.fixture(scope="session")
def beacon():
    p = subprocess.Popen([BEACON, '--port=%d' % BEACON_PORT, '--redis_port=7654', '--db_path='+BEACON_DB_PATH, '--posix_queue=0'])
    time.sleep(0.3) #wait for beacon to be really started
    beacon_connection = connection.Connection("localhost", BEACON_PORT)
    client._default_connection = beacon_connection
    cfg = static.get_config()
    yield cfg
    # finalization
    p.terminate()


    
