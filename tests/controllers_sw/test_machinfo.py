# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.counter import SamplingMode
from bliss.common.tango import DevSource


def test_machinfo_counters_issue1793(machinfo_tango_server, session):
    machinfo = session.config.get("machinfo")
    mg = session.config.get("issue1793_mg")
    for cnt in machinfo.counters:
        assert cnt.fullname in mg.available


def test_machinfo_conn_issue2333(machinfo_tango_server, session):
    machinfo = session.config.get("machinfo")
    p1 = machinfo.proxy
    assert p1 is machinfo.proxy  # check always the same proxy instance
    # check the counter controller is using the same instance
    assert (
        machinfo.counters.current._counter_controller._proxy is p1
    )  # check the counter controller is using the same instance
    assert all(cnt.mode == SamplingMode.SINGLE for cnt in machinfo.counters)
    assert machinfo.proxy.get_source() == DevSource.CACHE_DEV
