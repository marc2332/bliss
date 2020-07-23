# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


def test_machinfo_counters_issue1793(machinfo_tango_server, session):
    machinfo = session.config.get("machinfo")
    mg = session.config.get("issue1793_mg")
    for cnt in machinfo.counters:
        assert cnt.fullname in mg.available
