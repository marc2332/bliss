# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import numpy
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning import scan, chain
from bliss.scanning.acquisition import timer, calc, motor, counter
from bliss.common import event

def test_ascan_gauss_cen(beacon):
    session = beacon.get("test_session")
    session.setup()

    counter_class = getattr(setup_globals, 'AutoScanGaussianCounter')
    roby = getattr(setup_globals, 'roby')
    counter = counter_class("gaussianCurve")

    s = scans.ascan(roby, 0, 10, 10, 0, counter, save=False, return_scan=True)

    p = s.peak(counter)
    fwhm = s.fwhm(counter)
    c = s.com(counter)

    assert pytest.approx(p, 5)
    assert pytest.approx(fwhm, 2.3548) #std dev is 1
    assert pytest.approx(c, 5)
 
