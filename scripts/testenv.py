#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Launch Beacon, Redis, TangoDb and LimaCCD for the test configuration
"""

import os
from contextlib import contextmanager
import subprocess
import socket
from contextlib import closing
from time import sleep
import bliss
from bliss.config import get_sessions_list
from nexus_writer_service.io.io_utils import temproot, tempname


def find_free_port():
    """
    Find an unused port
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def bliss_test_db():
    db_path = os.path.normpath(
        os.path.join(bliss.__file__, "..", "..", "tests", "test_configuration")
    )
    if not os.path.isdir(db_path):
        raise RuntimeError(repr(db_path), " is not the bliss test db")
    return db_path


@contextmanager
def beacon():
    params = {}
    params["db_path"] = bliss_test_db()
    params["port"] = find_free_port()
    params["tango_port"] = find_free_port()
    params["redis_port"] = find_free_port()
    params["webapp_port"] = find_free_port()
    path = temproot()
    sockname = tempname(prefix="redis_", suffix=".sock")
    while os.path.exists(os.path.join(path, sockname)):
        sockname = tempname(prefix="redis_", suffix=".sock")
    params["redis_socket"] = os.path.join(path, sockname)
    params["log_level"] = "WARN"
    params["tango_debug_level"] = 0
    cliargs = ["beacon-server"]
    cliargs += ["--{}={}".format(k, v) for k, v in params.items()]

    env = {}
    env["BEACON_HOST"] = socket.gethostname() + ":{}".format(params["port"])
    env["TANGO_HOST"] = socket.gethostname() + ":{}".format(params["tango_port"])
    prefix = " ".join(["{}={}".format(k, v) for k, v in env.items()])
    os.environ.update(env)
    env["PATH"] = os.environ["PATH"]

    p = subprocess.Popen(cliargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("\nStart process (DONE):\n " + " ".join(cliargs))
    try:
        yield env, prefix
    finally:
        p.terminate()


@contextmanager
def lima(env=None, name="simulator"):
    cliargs = ["LimaCCDs", name]
    p = subprocess.Popen(
        cliargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
    )
    print("\nStart process (DONE):\n " + " ".join(cliargs))
    try:
        yield
    finally:
        p.terminate()


def print_env_info(prefix):
    print("\nAll session in the bliss test configuration:")
    print(" " + "\n ".join(get_sessions_list()))
    print("\nAttach basic external writer to session:")
    print(
        " {} NexusSessionWriter nexus_writer_base --noconfig --log=info".format(prefix)
    )
    print("\nStart CLI to session for basic writer testing:")
    print(" {} bliss -s nexus_writer_base --no-tmux".format(prefix))
    print("\nAttach configurable writer to session:")
    print(" {} NexusSessionWriter nexus_writer_config --log=info".format(prefix))
    print("\nStart CLI to session for configurable writer:")
    print(" {} bliss -s nexus_writer_config --no-tmux".format(prefix))
    input("\nPress any key to stop the servers")


if __name__ == "__main__":
    with beacon() as (env, prefix):
        sleep(5)  # Do someting more intelligent
        with lima(env, name="simulator"):
            with lima(env, name="simulator2"):
                print_env_info(prefix)
