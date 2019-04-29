# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_custom_attribute_read(roby, robz):
    assert roby.get_cust_attr_float() == pytest.approx(6.28, 1e-3)
    assert robz.get_cust_attr_float() == pytest.approx(3.14, 1e-3)


def test_custom_attribute_rw(robz):
    assert robz.get_voltage() == 220
    robz.set_voltage(380)
    assert robz.get_voltage() == 380
    robz.set_voltage(110)
