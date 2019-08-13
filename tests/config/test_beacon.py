# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.conductor import client
from bliss.config import static
import socket
import os


def test_redis_client_name(redis_conn):
    conn_name = f"{socket.gethostname()}:{os.getpid()}"
    client_id = str(redis_conn.client_id())
    client_list = redis_conn.execute_command("CLIENT LIST")
    for client_info in client_list:
        if client_info.get("id") == client_id:
            assert conn_name == client_info.get("name")
            break
    else:
        assert False


def test_config_base_path(beacon):
    saved_cfg = static.CONFIG
    static.CONFIG = None
    try:
        cfg = static.get_config(base_path="./sessions")
        assert "test_session" in cfg.names_list
    finally:
        cfg.close()
        static.CONFIG = saved_cfg
