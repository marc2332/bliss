# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.physics.hkl import geometry, sample
import math
import pytest


@pytest.fixture
def e4cv_test():
    """Returns the E4CV geometry and a sample
    defined with 2 reflections:
        - (1, 0, 0), {"omega": 30, "chi": 0, "phi": 90, "tth": 60}
        - (0, 1, 0), {"omega": 30, "chi": 0, "phi": 0, "tth": 60}
    """
    geo = geometry.HklGeometry("E4CV")
    smp = geo.get_sample()
    smp.add_one_reflection((1, 0, 0), {"omega": 30, "chi": 0, "phi": 90, "tth": 60})
    smp.add_one_reflection((0, 1, 0), {"omega": 30, "chi": 0, "phi": 0, "tth": 60})
    smp.computeUB()
    return geo, smp


e4cv_geo_info = "GEOMETRY : E4CV\nENERGY : 8.050922077922078 KeV\nPHYSICAL AXIS :\n - omega    [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n - chi      [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n - phi      [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n - tth      [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n\nMODES : \n --engine--      - --mode--                       { --parameters-- }\n HKL        [RW] * bissector                     \n HKL        [RW]   constant_omega                \n HKL        [RW]   constant_chi                  \n HKL        [RW]   constant_phi                  \n HKL        [RW]   double_diffraction             {'h2': 1.0, 'k2': 1.0, 'l2': 1.0}\n HKL        [RW]   psi_constant                   {'h2': 1.0, 'k2': 1.0, 'l2': 1.0, 'psi': 0.0}\n PSI        [RW] * psi                            {'h2': 1.0, 'k2': 1.0, 'l2': 1.0}\n Q          [RW] * q                             \n INCIDENCE  [RO] * incidence                      {'x': 0.0, 'y': 1.0, 'z': 0.0}\n\nPSEUDO AXIS :\n --engine-- - --name--   [-motor- ]\n HKL        - h          [        ] =   0.0000\n HKL        - k          [        ] =   0.0000\n HKL        - l          [        ] =   0.0000\n PSI        - psi        [        ] =   0.0000\n Q          - q          [        ] =   0.0000\n INCIDENCE  - incidence  [        ] =   0.0000\n INCIDENCE  - azimuth    [        ] =   0.0000\n"

smp_info = "SAMPLE : noname\nLATTICE (lengths / angles):\n         real space = 1.54 1.54 1.54 / 90 90 90\n   reciprocal space = 4.08 4.08 4.08 / 90 90 90\n\nUB (busing_levy):\n[[ 4.07999046e+00 -1.13800578e-15 -2.49827363e-16]\n [ 0.00000000e+00  0.00000000e+00 -4.07999046e+00]\n [ 8.88178420e-16  4.07999046e+00 -2.49827363e-16]]\n\nREFLECTIONS (H K L -omega- -chi- -phi- -tth- lambda):\n [0] :  1.0 0.0 0.0    30.0000     0.0000    90.0000    60.0000 1.54\n [1] :  0.0 1.0 0.0    30.0000     0.0000     0.0000    60.0000 1.54\n"


def test_reflections(e4cv_test):
    geo, smp = e4cv_test
    assert geo.info() == e4cv_geo_info

    assert smp.info() == smp_info

    (meas, theo) = smp.get_one_reflection_angles(0, 1)

    assert meas == pytest.approx(theo)


def test_engine(e4cv_test):
    geo, smp = e4cv_test

    # try set/get hkl mode and parameters
    hkl = geo._engines["hkl"]
    assert hkl.get_modes() == [
        "bissector",
        "constant_omega",
        "constant_chi",
        "constant_phi",
        "double_diffraction",
        "psi_constant",
    ]
    hkl.set_current_mode("psi_constant")
    assert hkl.get_current_mode() == "psi_constant"
    assert hkl.get_parameters() == {"h2": 1.0, "k2": 1.0, "l2": 1.0, "psi": 0.0}
    hkl.set_parameters({"psi": 60.0})
    assert hkl.get_parameters()["psi"] == pytest.approx(60.0)

    # work in bissector mode
    geo.set_mode("hkl", "bissector")
    assert geo.get_mode("hkl") == "bissector"

    geo.set_axis_pos({"omega": 30, "chi": 0, "phi": 90, "tth": 60})
    pos = geo.get_axis_pos()
    assert pos["omega"] == pytest.approx(30)
    assert pos["phi"] == pytest.approx(90)
    assert pos["tth"] == pytest.approx(60)
    pseudo_pos = geo.get_pseudo_pos()
    assert pseudo_pos["hkl_h"] == pytest.approx(1)
    assert pseudo_pos["hkl_k"] == pytest.approx(0)
    assert pseudo_pos["hkl_l"] == pytest.approx(0)
    assert pseudo_pos["psi_psi"] == pytest.approx(-135)
    assert pseudo_pos["q_q"] == pytest.approx(4.08, 1e-4)

    geo.set_axis_pos({"phi": 0.0})
    pseudo_pos = geo.get_pseudo_pos()
    assert pseudo_pos["hkl_h"] == pytest.approx(0)
    assert pseudo_pos["hkl_k"] == pytest.approx(1)
    assert pseudo_pos["hkl_l"] == pytest.approx(0)
    assert pseudo_pos["psi_psi"] == pytest.approx(-45)
    assert pseudo_pos["q_q"] == pytest.approx(4.08, 1e-4)

    # set hkl=100
    geo.set_pseudo_pos({"hkl_h": 1, "hkl_k": 0, "hkl_l": 0})
    pos = geo.get_axis_pos()
    assert pos["omega"] == pytest.approx(30)
    assert pos["phi"] == pytest.approx(90)
    assert pos["tth"] == pytest.approx(60)

    # set hkl=010
    geo.set_pseudo_pos({"hkl_h": 0, "hkl_k": 1, "hkl_l": 0})
    pos = geo.get_axis_pos()
    assert pos["omega"] == pytest.approx(30)
    assert pos["phi"] == pytest.approx(0, abs=1e-6)
    assert pos["tth"] == pytest.approx(60)

    # set constat_omega mode
    # geo.set_mode("hkl", "constant_omega")


def test_6c():
    geo = geometry.HklGeometry("E6C")
    # print((geo.info()))
