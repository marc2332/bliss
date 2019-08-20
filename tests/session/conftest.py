# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


@pytest.fixture
def session2(beacon):
    session = beacon.get("test_session2")
    yield session
    session.close()


@pytest.fixture
def session3(beacon):
    session = beacon.get("test_session3")
    yield session
    session.close()


@pytest.fixture
def session4(beacon):
    session = beacon.get("test_session4")
    yield session
    session.close()
