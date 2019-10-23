# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import subprocess
import gevent


@pytest.fixture
def nexus_writer(beacon, session, scan_tmpdir, wait_for_fixture):
    """
    this fixture is supposed to launch the tango server for the external writer
    but for the time being it just starts a subprossess
    
    """
    wait_for = wait_for_fixture

    nx_writer = ["NexusWriter", "-s", session.name, "--log=info"]
    p = subprocess.Popen(nx_writer, stdout=subprocess.PIPE)

    with gevent.Timeout(10, RuntimeError("Nexus Writer not running")):
        wait_for(p.stdout, "Start listening to scans")

    print("tata")

    # modify saving related settings of session
    session.env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)
    session.env_dict["SCAN_SAVING"].writer = "null"

    with gevent.Timeout(1, RuntimeError("no answer from NexusWriter")):
        p.stdout.read1()

    yield (session, p.stdout)

    p.terminate()
