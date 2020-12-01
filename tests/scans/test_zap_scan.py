# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
from bliss.common.scans.simulation import simu_l2scan, simu_mesh


def test_zap(session, images_directory):

    img_path = os.path.join(str(images_directory), "bliss_logo.png")

    fast_motor = session.config.get("roby")
    slow_motor = session.config.get("robz")
    cnt = session.config.get("diode")
    simu_l2scan(
        fast_motor,
        0,
        3,
        3,
        slow_motor,
        0,
        1,
        1,
        0.01,
        cnt,
        backnforth=False,
        scale=0.1,
        imshow=False,
        simdatapath=img_path,
    )


def test_simul_mesh(session, images_directory):

    img_path = os.path.join(str(images_directory), "bliss_logo.png")

    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode = session.config.get("diode")
    simu_mesh(roby, robz, diode, size=(3, 3), imshow=False, simdatapath=img_path)
