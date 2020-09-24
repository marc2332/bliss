# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
Tests for Vacuum Gauge controller reading VacGauge Tango DS.

* test_configuration/vac_gauge.yml
* tests/dummy_tg_server.py
* bliss/controllers/vacuum_gauge.py

To run isolated test:
  pytest tests/test_vacgauge.py -k test_vacgauge
"""


def test_vacgauge(beacon, dummy_tango_server, caplog):
    gauge = beacon.get("vacgauge")

    assert gauge.name == "vacgauge"
    assert gauge.pressure == 0.000000012345678
    assert gauge.proxy.name() == "id00/tango/dummy"
