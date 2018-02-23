# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
from bliss.common import event
import numpy

def test_traj_from_calc(s1hg):
    tg = s1hg.scan_on_trajectory(0, 5, 100, 0.01)
    trajectories = tg.trajectories

    assert set([t.axis.name for t in trajectories]) == set(['s1u', 's1d', 's1f', 's1b'])
    
    for traj in trajectories:
        if traj.axis.name in ('s1u', 's1d'):
            assert not numpy.any(traj.pvt['position'])
        elif traj.axis.name in ('s1f', 's1b'):
            assert pytest.approx(traj.pvt[:-1]['position'], 2.5)
        assert len(traj.pvt) == 100+2 #include start, final extra points for traj.

def test_traj_from_calc_from_calc(calc_mot2):
    tg = calc_mot2.scan_on_trajectory(0, 1, 100, 0.1)

    assert False



        

