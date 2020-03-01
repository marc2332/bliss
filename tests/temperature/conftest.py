# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


@pytest.fixture
def temp_tin(beacon):
    m = beacon.get("thermo_sample")
    yield m


@pytest.fixture
def temp_tout(beacon):
    m = beacon.get("heater")
    yield m


@pytest.fixture
def temp_tloop(beacon):
    m = beacon.get("sample_regulation")
    yield m
