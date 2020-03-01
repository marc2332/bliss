# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

SP = 10
SP = 15
SP = 20

"""
PyTest list of tests
"""


def test_custom_attr(temp_tout):
    assert temp_tout.get_material() == "Hg"
    temp_tout.set_material("CH4OH")
    assert temp_tout.get_material() == "CH4OH"


def test_custom_cmd(temp_tin):
    assert temp_tin.get_double_str("calor") == "calor_calor"
