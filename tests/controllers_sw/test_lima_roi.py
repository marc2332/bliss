# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.controllers.lima import roi as lima_roi


@pytest.mark.parametrize(
    "testcase",
    [
        (lima_roi.Roi(0, 1, 20, 30), dict(x=0, y=1, width=20, height=30, kind="rect")),
        (
            lima_roi.ArcRoi(0, 1, 20, 30, 200, 300),
            dict(cx=0, cy=1, r1=20, r2=30, a1=200, a2=300, kind="arc"),
        ),
        (
            lima_roi.RoiProfile(0, 1, 20, 30, "horizontal"),
            dict(x=0, y=1, width=20, height=30, mode="horizontal", kind="profile"),
        ),
    ],
)
def test_dict_to_roi(testcase):
    """Check that to_dict and `dict_to_roi` are symmetric"""
    roi, dico = testcase
    assert roi.to_dict() == dico
    roi2 = lima_roi.dict_to_roi(dico)
    assert roi == roi2


@pytest.mark.parametrize(
    "testcase",
    [
        dict(x=0, y=1, width=20, height=30, kind="unknown"),
        dict(x="wrong_kind", y=1, width=20, height=30, kind="rect"),
        dict(unknown_arg=1, x=0, y=1, width=20, height=30, kind="rect"),
    ],
)
def test_wrong_dict(beacon, lima_simulator, testcase):
    with pytest.raises(ValueError):
        dico = testcase
        lima_roi.dict_to_roi(dico)
