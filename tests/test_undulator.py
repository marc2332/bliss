# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


def test_undulator(beacon, dummy_tango_server):
    u23a = beacon.get("u23a")

    # u23a is form ESRF_Undulator class
    # not a tang_attr_as_counter => no format control
    assert u23a.position == 1.4078913

    assert u23a.velocity == 5

    assert u23a.acceleration == 125
