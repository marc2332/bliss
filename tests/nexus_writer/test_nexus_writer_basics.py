# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import gevent


def test_NxW_receiving_events(beacon, nexus_writer):
    session, nexus_writer_out = nexus_writer

    diode = session.env_dict["diode"]
    s1 = scans.loopscan(10, .1, diode)

    # as we don't have any synchronisation for now
    gevent.sleep(.5)

    with gevent.Timeout(1, RuntimeError("no answer from NexusWriter")):
        out = nexus_writer_out.read1()

    assert b"DataNode '1_loopscan'" in out
