# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import redis
from bliss.config.conductor import client, connection


@pytest.fixture
def two_clients(beacon):
    conductor_conn = client.get_default_connection()
    conductor_conn.set_client_name("test1")
    client._default_connection = None  # force making a new connection
    conductor_conn2 = client.get_default_connection()
    conductor_conn2.set_client_name("test2")
    yield conductor_conn, conductor_conn2
    conductor_conn.close()
    conductor_conn2.close()


@pytest.fixture
def new_beacon_connection(ports, clean_socket):
    redis_db = redis.Redis(port=ports.redis_port)
    redis_db.flushall()
    redis_data_db = redis.Redis(port=ports.redis_data_port)
    redis_data_db.flushall()
    conn = connection.Connection("localhost", ports.beacon_port)
    yield conn
    conn.close()
