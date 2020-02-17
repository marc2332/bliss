# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


@pytest.fixture
def temp_tloop(beacon):
    l = beacon.get("sample_regulation_new")
    yield l
    l.close()
    l.controller.close()


@pytest.fixture
def temp_soft_tloop(beacon):
    l = beacon.get("soft_regul")
    yield l
    l.close()
    l.input.device.close()


@pytest.fixture
def temp_soft_tloop_2(beacon):
    l = beacon.get("soft_regul2")
    yield l
    l.close()
    l.input.device.close()
