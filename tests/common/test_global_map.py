# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent

from bliss import global_map
from ..conftest import GreenletsContext


@pytest.fixture
def bad_motor(default_session):
    bad_motor = default_session.config.get("bad")
    bad_motor.controller.position_reading_delay = 1

    yield bad_motor

    bad_motor.controller.position_reading_delay = 0


def test_issue_2410(bad_motor):
    greenlets_context = GreenletsContext()
    with greenlets_context:
        with pytest.raises(gevent.Timeout):
            with gevent.Timeout(0.1):
                list(global_map.get_axes_positions_iter(on_error="ERR"))
    assert greenlets_context.all_resources_released
