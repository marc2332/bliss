# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy as np


# @pytest.fixture
# def e4cv_test():
#     """Returns the E4CV geometry and a sample
#     defined with 2 reflections:
#         - (1, 0, 0), {"omega": 30, "chi": 0, "phi": 90, "tth": 60}
#         - (0, 1, 0), {"omega": 30, "chi": 0, "phi": 0, "tth": 60}
#     """
#     geo = geometry.HklGeometry("E4CV")
#     smp = geo.get_sample()
#     smp.add_one_reflection((1, 0, 0), {"omega": 30, "chi": 0, "phi": 90, "tth": 60})
#     smp.add_one_reflection((0, 1, 0), {"omega": 30, "chi": 0, "phi": 0, "tth": 60})
#     smp.computeUB()
#     return geo, smp


# e4cv_geo_info = "GEOMETRY : E4CV\nENERGY : 8.050922077922078 KeV\nPHYSICAL AXIS :\n - omega    [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n - chi      [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n - phi      [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n - tth      [no-motor] =   0.0000 Degree limits= (-180.0,180.0)\n\nMODES : \n --engine--      - --mode--                       { --parameters-- }\n HKL        [RW] * bissector                     \n HKL        [RW]   constant_omega                \n HKL        [RW]   constant_chi                  \n HKL        [RW]   constant_phi                  \n HKL        [RW]   double_diffraction             {'h2': 1.0, 'k2': 1.0, 'l2': 1.0}\n HKL        [RW]   psi_constant                   {'h2': 1.0, 'k2': 1.0, 'l2': 1.0, 'psi': 0.0}\n PSI        [RW] * psi                            {'h2': 1.0, 'k2': 1.0, 'l2': 1.0}\n Q          [RW] * q                             \n INCIDENCE  [RO] * incidence                      {'x': 0.0, 'y': 1.0, 'z': 0.0}\n\nPSEUDO AXIS :\n --engine-- - --name--   [-motor- ]\n HKL        - h          [        ] =   0.0000\n HKL        - k          [        ] =   0.0000\n HKL        - l          [        ] =   0.0000\n PSI        - psi        [        ] =   0.0000\n Q          - q          [        ] =   0.0000\n INCIDENCE  - incidence  [        ] =   0.0000\n INCIDENCE  - azimuth    [        ] =   0.0000\n"

# smp_info = "SAMPLE : noname\nLATTICE (lengths / angles):\n         real space = 1.54 1.54 1.54 / 90 90 90\n   reciprocal space = 4.08 4.08 4.08 / 90 90 90\n\nUB (busing_levy):\n[[ 4.07999046e+00 -1.13800578e-15 -2.49827363e-16]\n [ 0.00000000e+00  0.00000000e+00 -4.07999046e+00]\n [ 8.88178420e-16  4.07999046e+00 -2.49827363e-16]]\n\nREFLECTIONS (H K L -omega- -chi- -phi- -tth- lambda):\n [0] :  1.0 0.0 0.0    30.0000     0.0000    90.0000    60.0000 1.54\n [1] :  0.0 1.0 0.0    30.0000     0.0000     0.0000    60.0000 1.54\n"


# def test_reflections(e4cv_test):
#     geo, smp = e4cv_test
#     assert geo.info() == e4cv_geo_info

#     assert smp.info() == smp_info

#     (meas, theo) = smp.get_one_reflection_angles(0, 1)

#     assert meas == pytest.approx(theo)


# def test_engine(e4cv_test):
#     geo, smp = e4cv_test

#     # try set/get hkl mode and parameters
#     hkl = geo._engines["hkl"]
#     assert hkl.get_modes() == [
#         "bissector",
#         "constant_omega",
#         "constant_chi",
#         "constant_phi",
#         "double_diffraction",
#         "psi_constant",
#     ]
#     hkl.set_current_mode("psi_constant")
#     assert hkl.get_current_mode() == "psi_constant"
#     assert hkl.get_parameters() == {"h2": 1.0, "k2": 1.0, "l2": 1.0, "psi": 0.0}
#     hkl.set_parameters({"psi": 60.0})
#     assert hkl.get_parameters()["psi"] == pytest.approx(60.0)

#     # work in bissector mode
#     geo.set_mode("hkl", "bissector")
#     assert geo.get_mode("hkl") == "bissector"

#     geo.set_axis_pos({"omega": 30, "chi": 0, "phi": 90, "tth": 60})
#     pos = geo.get_axis_pos()
#     assert pos["omega"] == pytest.approx(30)
#     assert pos["phi"] == pytest.approx(90)
#     assert pos["tth"] == pytest.approx(60)
#     pseudo_pos = geo.get_pseudo_pos()
#     assert pseudo_pos["hkl_h"] == pytest.approx(1)
#     assert pseudo_pos["hkl_k"] == pytest.approx(0)
#     assert pseudo_pos["hkl_l"] == pytest.approx(0)
#     assert pseudo_pos["psi_psi"] == pytest.approx(-135)
#     assert pseudo_pos["q_q"] == pytest.approx(4.08, 1e-4)

#     geo.set_axis_pos({"phi": 0.0})
#     pseudo_pos = geo.get_pseudo_pos()
#     assert pseudo_pos["hkl_h"] == pytest.approx(0)
#     assert pseudo_pos["hkl_k"] == pytest.approx(1)
#     assert pseudo_pos["hkl_l"] == pytest.approx(0)
#     assert pseudo_pos["psi_psi"] == pytest.approx(-45)
#     assert pseudo_pos["q_q"] == pytest.approx(4.08, 1e-4)

#     # set hkl=100
#     geo.set_pseudo_pos({"hkl_h": 1, "hkl_k": 0, "hkl_l": 0})
#     pos = geo.get_axis_pos()
#     assert pos["omega"] == pytest.approx(30)
#     assert pos["phi"] == pytest.approx(90)
#     assert pos["tth"] == pytest.approx(60)

#     # set hkl=010
#     geo.set_pseudo_pos({"hkl_h": 0, "hkl_k": 1, "hkl_l": 0})
#     pos = geo.get_axis_pos()
#     assert pos["omega"] == pytest.approx(30)
#     assert pos["phi"] == pytest.approx(0, abs=1e-6)
#     assert pos["tth"] == pytest.approx(60)

#     # set constat_omega mode
#     # geo.set_mode("hkl", "constant_omega")


# def test_6c():
#     geo = geometry.HklGeometry("E6C")
#     # print((geo.info()))


def test_zaxis(default_session):
    import bliss.common.hkl as hkl

    """

    GEOMETRY : ZAXIS
    ENERGY : 25.39998811784638 KeV
    PHYSICAL AXIS :
    - mu       [roby    ] =   0.1000 Degree limits= (-360.0,360.0)
    - omega    [robu    ] =  53.2179 Degree limits= (-360.0,360.0)
    - delta    [robz    ] =  11.7265 Degree limits= (-360.0,360.0)
    - gamma    [robz2   ] =   6.5295 Degree limits= (-360.0,360.0)

    MODES :
    --engine--      - --mode--        { --parameters-- }
    HKL        [RW] * zaxis
    HKL        [RW]   reflectivity
    Q2         [RW] * q2
    QPER_QPAR  [RW] * qper_qpar       {'x': 0.0, 'y': 1.0, 'z': 0.0}
    TTH2       [RW] * tth2
    INCIDENCE  [RO] * incidence       {'x': 0.0, 'y': 1.0, 'z': 0.0}
    EMERGENCE  [RO] * emergence       {'x': 0.0, 'y': 1.0, 'z': 0.0}

    PSEUDO AXIS :
    --engine-- - --name--   [-motor- ]
    HKL        - h          [Hz      ] =   1.0015
    HKL        - k          [Kz      ] =   1.0015
    HKL        - l          [Lz      ] =   3.0046
    Q2         - q          [        ] =   3.0145
    Q2         - alpha      [        ] =  60.2490
    QPER_QPAR  - qper       [        ] =   1.4862
    QPER_QPAR  - qpar       [        ] =   2.6227
    TTH2       - tth        [        ] =  13.4489
    TTH2       - alpha      [        ] =  60.2490
    INCIDENCE  - incidence  [        ] =   0.1000
    INCIDENCE  - azimuth    [        ] =   0.0000
    EMERGENCE  - emergence  [        ] =   6.5295
    EMERGENCE  - azimuth    [        ] =   0.0000

    z.wavelength = 0.488127

    reflist = ((1.0, 1.0, 3.0, 0.1, 53.2179, 11.7265, 6.5295), (2.0, -1.0, 3.0, 0.1, -6.761, 11.7369, 6.5328))

    z.check_hklscan((0,1,0), (0,1,6), 10)

          H        K        L       roby       robu       robz      robz2
      0.0000   1.0000   0.0000     0.1000    78.7755     6.7811    -0.0422
      0.0000   1.0000   0.6667     0.1000    79.0414     6.7698     1.3927
      0.0000   1.0000   1.3333     0.1000    79.6139     6.7604     2.8285
      0.0000   1.0000   2.0000     0.1000    80.4951     6.7520     4.2660
      0.0000   1.0000   2.6667     0.1000    81.6877     6.7431     5.7063
      0.0000   1.0000   3.3333     0.1000    83.1955     6.7317     7.1502
      0.0000   1.0000   4.0000     0.1000    85.0235     6.7150     8.5986
      0.0000   1.0000   4.6667     0.1000    87.1792     6.6896    10.0527
      0.0000   1.0000   5.3333     0.1000    89.6728     6.6511    11.5132
      0.0000   1.0000   6.0000     0.1000    92.5196     6.5941    12.9815

    """
    lattice = (4.765, 4.765, 12.994, 90.0, 90.0, 119.99999999999999)
    energy = 25.39998811784638
    hkl_or0 = (1.0, 1.0, 3.0)
    hkl_or1 = (2.0, -1.0, 3.0)
    pos_or0 = {"mu": 0.1, "omega": 53.2179, "delta": 11.7265, "gamma": 6.5295}
    pos_or1 = {"mu": 0.1, "omega": -6.761, "delta": 11.7369, "gamma": 6.5328}
    reflist = (hkl_or0 + tuple(pos_or0.values()), hkl_or1 + tuple(pos_or1.values()))

    diode = default_session.config.get("diode")
    mu = default_session.config.get("roby")
    omega = default_session.config.get("robu")
    delta = default_session.config.get("robz")
    gamma = default_session.config.get("robz2")

    mu.limits = (-180, 180)
    omega.limits = (-180, 180)
    delta.limits = (-180, 180)
    gamma.limits = (-180, 180)

    z = default_session.config.get("zaxis")
    z.lattice = lattice
    z.energy = energy

    hkl.setmode("zaxis")

    mu.move(pos_or0["mu"])
    omega.move(pos_or0["omega"])
    delta.move(pos_or0["delta"])
    gamma.move(pos_or0["gamma"])
    assert z.pos == tuple(pos_or0.values())
    hkl.or0(*hkl_or0)

    mu.move(pos_or1["mu"])
    omega.move(pos_or1["omega"])
    delta.move(pos_or1["delta"])
    gamma.move(pos_or1["gamma"])
    assert z.pos == tuple(pos_or1.values())
    hkl.or1(*hkl_or1)

    assert z.reflist == reflist

    hkl.setor0(*reflist[0])
    hkl.setor1(*reflist[1])
    assert z.reflist == reflist

    hkl.freeze(0.1)  # freeze mu => roby

    hkl.br(1.0, 1.0, 6.0)
    hkl.ubr(1.0, 1.0, 1.0)
    hkl.ca(1.0, 1.0, 6.0)
    hkl.ci(*z.pos)
    hkl.wh()
    hkl.pa()

    hkl.unfreeze()
    hkl.freeze(0.1)
    hkl.pr_freeze()

    hkl.or_swap()
    assert z.reflist == (reflist[1], reflist[0])
    hkl.or_swap()
    assert z.reflist == reflist

    hkl.refdel(1)
    hkl.refadd(*reflist[1])
    assert z.reflist == reflist

    hkl.paUB()
    hkl.showUB()
    hkl.geolimits()

    hkl.hscan(1, 2, 10, 0.1, diode)
    hkl.kscan(1, 2, 10, 0.1, diode)
    hkl.lscan(1, 2, 10, 0.1, diode)
    s = hkl.hklscan((0, 1, 0), (0, 1, 6), 10, 0.1, diode)

    assert np.all(
        np.isclose(
            s.get_data("Hz"),
            np.array([0., 0., 0., 0., 0., 0., 0., 0., 0., 0.]),
            rtol=1e-05,
            atol=1e-05,
        )
    )
    assert np.all(
        np.isclose(
            s.get_data("Kz"),
            np.array([1., 1., 1., 1., 1., 1., 1., 1., 1., 1.]),
            rtol=1e-05,
            atol=1e-05,
        )
    )
    assert np.all(
        np.isclose(
            s.get_data("Lz"),
            np.array(
                [0.0, 0.6667, 1.3333, 2.0, 2.6667, 3.3333, 4.0, 4.6667, 5.3333, 6.0]
            ),
            rtol=1e-05,
            atol=1e-04,
        )
    )

    assert np.all(
        np.isclose(
            s.get_data("roby"),
            np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]),
            rtol=1e-05,
            atol=1e-05,
        )
    )
    assert np.all(
        np.isclose(
            s.get_data("robu"),
            np.array(
                [
                    78.7755,
                    79.0414,
                    79.6139,
                    80.4951,
                    81.6877,
                    83.1955,
                    85.0235,
                    87.1792,
                    89.6728,
                    92.5196,
                ]
            ),
            rtol=1e-05,
            atol=1e-05,
        )
    )
    assert np.all(
        np.isclose(
            s.get_data("robz"),
            np.array(
                [
                    6.7811,
                    6.7698,
                    6.7604,
                    6.7520,
                    6.7431,
                    6.7317,
                    6.7150,
                    6.6896,
                    6.6511,
                    6.5941,
                ]
            ),
            rtol=1e-05,
            atol=1e-05,
        )
    )
    assert np.all(
        np.isclose(
            s.get_data("robz2"),
            np.array(
                [
                    -0.0422,
                    1.3927,
                    2.8285,
                    4.2660,
                    5.7063,
                    7.1502,
                    8.5986,
                    10.0527,
                    11.5132,
                    12.9815,
                ]
            ),
            rtol=1e-05,
            atol=1e-05,
        )
    )

    hkl.hdscan(1, 2, 10, 0.1, diode)
    hkl.kdscan(1, 2, 10, 0.1, diode)
    hkl.ldscan(1, 2, 10, 0.1, diode)
    hkl.hkldscan((0, 1, 0), (0, 1, 6), 10, 0.1, diode)

    z._close()
