# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_opiom_init(beacon, dummy_tango_server):
    _, dummy_tango_server = dummy_tango_server

    dummy_tango_server.emulate_device("opiom")

    opiom = beacon.get("opiom1")
    assert opiom
