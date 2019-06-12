# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Test diffraction physics"""

from functools import partial

from numpy import pi, array
from pytest import raises, approx

from bliss.physics.diffraction import HKL, Crystal, Si
from bliss.physics.diffraction import CrystalPlane, MultiPlane
from bliss.physics.diffraction import string_to_crystal_plane
from bliss.physics.diffraction import distance_lattice_diffraction_plane

import bliss.physics.diffraction as diff
import bliss.physics.spectroscopy as spectro

# Patch default 1e-12 default value for abs
approx = partial(approx, rel=1e-3, abs=0.)


def test_hkl():
    # invalid hkl formats

    with raises(ValueError) as err:
        HKL.fromstring("1234")

    with raises(ValueError) as err:
        HKL.fromstring("1 10")

    with raises(ValueError) as err:
        HKL.fromstring("1 1 0 0")

    with raises(ValueError) as err:
        HKL.fromstring("nil")

    # valid hkl

    plane110 = HKL.fromstring("110")
    assert isinstance(plane110, HKL)
    assert plane110.h == 1
    assert plane110.k == 1
    assert plane110.l == 0
    assert plane110 == (1, 1, 0)
    assert plane110 == HKL(1, 1, 0)
    assert plane110 == HKL.fromstring("1 1 0")
    assert plane110.tostring() == "110"

    plane111111 = HKL.fromstring("11 11 11")
    assert isinstance(plane111111, HKL)
    assert plane111111.h == 11
    assert plane111111.k == 11
    assert plane111111.l == 11
    assert plane111111 == HKL(11, 11, 11)
    assert plane111111 == (11, 11, 11)
    assert plane111111.tostring() == "11 11 11"


def test_distance_lattice_diffraction_plane():
    Si_a = 5.4307e-10  # (m)
    Si_110_d = 3.8401e-10  # (m)

    d1 = distance_lattice_diffraction_plane(1, 1, 0, Si_a)
    assert d1 == approx(Si_110_d)


def test_crystal():
    b_theta = pi / 8  # (rad)
    b_energy = 6.759e-16  # (J)

    b_thetas = array((pi / 8, pi / 12))
    b_energies = array((6.759e-16, 9.995e-16))

    assert isinstance(Si, Crystal)

    assert repr(Si) == "Si"
    assert Si.bragg_energy(b_theta, "110") == approx(b_energy)
    assert Si.bragg_angle(b_energy, "110") == approx(b_theta)
    assert Si.bragg_energy(b_thetas, "110") == approx(b_energies)
    assert Si.bragg_angle(b_energies, "110") == approx(b_thetas)

    Si_2 = Crystal(("Si", 5.4307e-10))

    assert repr(Si_2) == "Si"
    assert Si_2.bragg_energy(b_theta, "110") == approx(b_energy)
    assert Si_2.bragg_angle(b_energy, "110") == approx(b_theta)
    assert Si_2.bragg_energy(b_thetas, "110") == approx(b_energies)
    assert Si_2.bragg_angle(b_energies, "110") == approx(b_thetas)


def test_crystal_plane():
    b_theta = pi / 8  # (rad)
    b_energy = 6.759e-16  # (J)

    b_thetas = array((pi / 8, pi / 12))
    b_energies = array((6.759e-16, 9.995e-16))

    crystal_plane110 = "Si110"
    crystal_plane111111 = "Si(11 11 11)"

    Si110 = Si("110")

    assert repr(Si110) == "Si(110)"
    assert Si110.bragg_energy(b_theta) == approx(b_energy)
    assert Si110.bragg_angle(b_energy) == approx(b_theta)
    assert Si110.bragg_energy(b_thetas) == approx(b_energies)
    assert Si110.bragg_angle(b_energies) == approx(b_thetas)

    Si110_2 = CrystalPlane(Si, HKL(1, 1, 0))

    assert Si110_2.bragg_energy(b_theta) == approx(b_energy)
    assert Si110_2.bragg_angle(b_energy) == approx(b_theta)
    assert Si110_2.bragg_energy(b_thetas) == approx(b_energies)
    assert Si110_2.bragg_angle(b_energies) == approx(b_thetas)

    Si110_parse1 = string_to_crystal_plane(crystal_plane110)
    Si110_parse2 = CrystalPlane.fromstring(crystal_plane110)

    assert isinstance(Si110_parse1, CrystalPlane)
    assert isinstance(Si110_parse2, CrystalPlane)
    assert Si110 is Si110_parse1
    assert Si110 is Si110_parse2

    Si111111 = Si("11 11 11")
    Si111111_parse1 = string_to_crystal_plane(crystal_plane111111)
    Si111111_parse2 = CrystalPlane.fromstring(crystal_plane111111)

    assert isinstance(Si111111_parse1, CrystalPlane)
    assert isinstance(Si111111_parse2, CrystalPlane)
    assert Si111111 is Si111111_parse1
    assert Si111111 is Si111111_parse2


def test_multi_plane():
    b_theta = pi / 8  # (rad)
    b_energy = 5.190e-16  # (J)

    b_thetas = array((pi / 8, pi / 12))
    b_energies = array((5.190e-16, 7.675e-16))

    multi = MultiPlane(distance=5e-10)

    assert repr(multi) == "MultiPlane(distance=5e-10)"
    print((multi.bragg_energy(b_theta)))
    assert multi.bragg_energy(b_theta) == approx(b_energy)
    assert multi.bragg_angle(b_energy) == approx(b_theta)
    assert multi.bragg_energy(b_thetas) == approx(b_energies)
    assert multi.bragg_angle(b_energies) == approx(b_thetas)


def test_w2e_e2w():
    # 7.5 keV ≈ 1.65 angstrom
    assert spectro.energy_kev_to_wavelength_angstrom(7.5) == approx(1.653122)

    # 1.653122 angstrom ≈ 7.5 keV
    assert spectro.wavelength_angstrom_to_energy_kev(1.653122) == approx(7.5)
