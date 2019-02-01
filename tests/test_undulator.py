# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_undulator(beacon, dummy_tango_server):
    u23a = beacon.get("u23a")

    assert u23a.position == 1.4
    assert u23a.velocity == 5
    assert u23a.acceleration == 125
