# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import gevent
import subprocess
from bliss.config.conductor import client


def test_single_bliss_session(ports, beacon):
    try:
        first_shell = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-c",
                "from bliss.shell.initialize import *; initialize('test_session'); import time; time.sleep(1000)",
            ],
            stdout=subprocess.PIPE,
        )
        # wait until setup is finished
        with gevent.Timeout(10):
            for line in first_shell.stdout:
                line = line.decode().strip()
                print(line)
                if line.startswith("Done"):
                    break

        # ok so check who locked
        beacon_client_conn = client.get_default_connection()
        assert (
            str(first_shell.pid)
            in beacon_client_conn.who_locked("test_session")["test_session"]
        )

        # start 2nd shell and check the exception
        second_shell = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from bliss.shell.initialize import *; initialize('test_session')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, err = second_shell.communicate()
        assert b"RuntimeError: lock timeout" in err
    finally:
        first_shell.terminate()
