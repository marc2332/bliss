# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import logging
import re

from bliss.common import timedisplay


def test_timedisplay():
    assert timedisplay.duration_format(123.456789) == "2mn 3s 456ms 789μs"
    assert timedisplay.duration_format(0.000123) == "123μs"
    assert timedisplay.duration_format(0.123000) == "123ms"
    assert timedisplay.duration_format(1234567.000000) == "14days 6h 56mn 7s"
