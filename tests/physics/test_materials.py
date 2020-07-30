# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import itertools
import numpy
import pytest
from bliss.physics import materials
from bliss.physics import backend


def _set_backend(name):
    try:
        backend.MaterialBackend.set_backend(name)
    except RuntimeError:
        pytest.skip(f"Backend {repr(name)} not installed")


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_element_compare(backend):
    _set_backend(backend)
    el1 = materials.Element("Fe")
    el2 = materials.Element("Fe")
    assert el1 == el2
    assert el1 == "Fe"
    assert str(el2) == "Fe"
    assert el1.density == el2.density
    assert el1.density is not None
    assert el1.molar_mass == el2.molar_mass
    assert el1.molar_mass is not None
    assert el1.Z == el2.Z
    assert el1.Z == 26
    assert el1.symbol == el2.symbol
    assert el1.symbol == "Fe"

    el1 = materials.Element("Fe")
    el2 = materials.Element("Al")
    assert el1 != el2
    assert el2 < el1
    assert el1 == "Fe"
    assert el2 == "Al"
    assert str(el1) == "Fe"
    assert str(el2) == "Al"
    assert el1.density != el2.density
    assert el1.density is not None
    assert el2.density is not None
    assert el1.molar_mass != el2.molar_mass
    assert el1.molar_mass is not None
    assert el2.molar_mass is not None
    assert el1.Z != el2.Z
    assert el1.Z == 26
    assert el2.Z == 13
    assert el1.symbol != el2.symbol
    assert el1.symbol == "Fe"
    assert el2.symbol == "Al"


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_compound_compare(backend):
    _set_backend(backend)
    c1 = materials.Compound("Fe2O3", density=5.25)
    c2 = materials.Compound("Fe2O3", density=5.25)
    assert c1 == c2
    assert c1 == (("O", 3), ("Fe", 2), 5.25)
    assert c2 == (("O", 3), ("Fe", 2), 5.25)
    assert str(c1) == "Fe2O3"
    assert str(c2) == "Fe2O3"
    assert c1.density == c2.density
    assert c1.density is not None
    assert c2.density is not None

    c1 = materials.Compound("Fe2O3", density=5.25)
    c2 = materials.Compound("Fe2O3", density=5.24)
    assert c1 != c2
    assert c2 < c1
    assert c1 == (("O", 3), ("Fe", 2), 5.25)
    assert c2 == (("O", 3), ("Fe", 2), 5.24)
    assert str(c1) == "Fe2O3"
    assert str(c2) == "Fe2O3"
    assert c1.density != c2.density
    assert c1.density is not None
    assert c2.density is not None

    c1 = materials.Compound("Fe2O3", density=5.25, name="Fe2O3a")
    c2 = materials.Compound("Fe2O3", density=5.25)
    assert c1 != c2
    assert c1 == "Fe2O3a"
    assert c2 == (("O", 3), ("Fe", 2), 5.25)
    assert str(c1) == "Fe2O3a"
    assert str(c2) == "Fe2O3"
    assert c1.density == c2.density
    assert c1.density is not None
    assert c2.density is not None


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_mixture_compare(backend):
    _set_backend(backend)
    c1 = materials.Compound("Fe2O3", density=5)
    c2 = materials.Compound("Al2O3", density=6)
    m1 = materials.Mixture({c1: 1, c2: 1}, kind="mole")
    m2 = materials.Mixture({c1: 1, c2: 1}, kind="mole")
    assert m1 == m2
    assert m1 == (("O", 6), ("Al", 2), ("Fe", 2), m1.density)
    assert m2 == (("O", 6), ("Al", 2), ("Fe", 2), m1.density)
    assert str(m1) == "Fe2O3Al2O3"
    assert str(m2) == "Fe2O3Al2O3"
    assert m1.density == m2.density
    assert m1.density is not None
    assert m2.density is not None


def test_formula_parser():
    parser = materials.FormulaParser()
    result = parser.eval("Pb3(CO3)2(OH)2")
    assert result == {"Pb": 3, "C": 2, "O": 8, "H": 2}


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_compound_simplify(backend):
    _set_backend(backend)
    c1 = materials.Compound("Fe2O3", density=5.25)
    c2 = c1.simplify()
    assert c1 == c2
    assert c1 == (("O", 3), ("Fe", 2), 5.25)
    assert c2 == (("O", 3), ("Fe", 2), 5.25)
    assert str(c1) == "Fe2O3"
    assert str(c2) == "Fe2O3"
    assert c1.density == c2.density
    assert c1.density is not None
    assert c2.density is not None

    el1 = materials.Element("Fe")
    c1 = materials.Compound("Fe")
    el2 = c1.simplify()
    assert el1 == el2
    assert el1 == "Fe"
    assert str(el2) == "Fe"
    assert el1.density == el2.density
    assert el1.density == c1.density
    assert el1.density is not None
    assert el1.molar_mass == el2.molar_mass
    assert el1.molar_mass == c1.molar_mass
    assert el1.molar_mass is not None
    assert el1.Z == el2.Z
    assert el1.Z == 26
    assert el1.symbol == el2.symbol
    assert el1.symbol == "Fe"


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_mixture_simplify(backend):
    _set_backend(backend)
    c0 = materials.Compound("Fe2O3", density=5.25)
    m1 = materials.Mixture({c0: 1, "Al": 1}, kind="mole")
    c1 = m1.simplify()
    c2 = materials.Compound("Fe2O3Al", density=c1.density)
    assert c1 == c2
    assert c1 == (("O", 3), ("Al", 1), ("Fe", 2), c1.density)
    assert c2 == (("O", 3), ("Al", 1), ("Fe", 2), c1.density)
    assert c1.density == c2.density
    assert m1.density == c1.density
    assert c1.molar_mass == c2.molar_mass
    assert m1.molar_mass != c1.molar_mass
    assert str(m1) == "Fe2O3Al"

    c1 = materials.Compound("Fe2O3", density=5.25)
    c2 = materials.Compound("Al2O3", density=3)
    m1 = materials.Mixture({c1: 1, c2: 1}, kind="mole")
    mat = materials.Mixture({m1: 1, c2: 1, "Al": 1}, kind="mole").simplify()
    assert mat == (("O", 9), ("Al", 5), ("Fe", 2), mat.density)
    assert str(mat) == "Fe2O9Al5"


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_compound_catalog(backend):
    _set_backend(backend)
    if backend != "xraylib":
        pytest.skip(f"Backend {repr(backend)} does not support compound catalogs")
    c1 = materials.Compound("water")
    c2 = materials.Compound("water")
    assert c1 == c2
    assert "water" in str(c1).lower()
    c2 = materials.Compound("air")
    assert c1 != c2
    assert "air" in str(c2).lower()


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_compound_calc_density(backend):
    _set_backend(backend)
    c1 = materials.Compound("Fe2O3", density=5.25)
    energy = 1
    thickness = 1e-4
    transmission = c1.transmission(energy, thickness)
    c1.density_from_transmission(energy, transmission, thickness)
    numpy.testing.assert_allclose(c1.density, 5.25)


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_compound_stoichiometry(backend):
    _set_backend(backend)
    cls = materials.Compound
    c1 = materials.Element("Fe")
    c2 = materials.Element("O")
    c3 = "Al"
    _test_stoichiometry(cls, c1, c2, c3)


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_mixture_stoichiometry(backend):
    _set_backend(backend)
    cls = materials.Mixture
    c1 = materials.Compound("Fe2O3", density=5.25)
    c2 = materials.Compound("Al2O3", density=3)
    m1 = materials.Mixture({c1: 1, c2: 1}, kind="mole")
    c3 = "Al"
    _test_stoichiometry(cls, c1, m1, c3)


def _test_stoichiometry(cls, c1, c2, c3):
    for a, b, c in itertools.permutations(["mole", "mass", "volume"]):
        iscompound = cls is materials.Compound
        if iscompound:
            mat1 = cls({c1: 1, c2: 1, c3: 1}, kind=a, density=3.4)
        else:
            mat1 = cls({c1: 1, c2: 1, c3: 1}, kind=a)

        if b == "mole":
            fractions = mat1.mole_fractions
        elif b == "volume":
            fractions = mat1.volume_fractions
        else:
            fractions = mat1.mass_fractions
        if iscompound:
            mat2 = cls(fractions, kind=b, density=mat1.density)
        else:
            mat2 = cls(fractions, kind=b)

        if c == "mole":
            fractions = mat1.mole_fractions
        elif c == "volume":
            fractions = mat1.volume_fractions
        else:
            fractions = mat1.mass_fractions
        if iscompound:
            mat3 = cls(fractions, kind=c, density=mat1.density)
        else:
            mat3 = cls(fractions, kind=c)

        assert_fractions_equal(mat1.mole_fractions, mat2.mole_fractions)
        assert_fractions_equal(mat1.mole_fractions, mat3.mole_fractions)
        assert_fractions_equal(mat2.mole_fractions, mat3.mole_fractions)

        assert_fractions_equal(mat1.volume_fractions, mat2.volume_fractions)
        assert_fractions_equal(mat1.volume_fractions, mat3.volume_fractions)
        assert_fractions_equal(mat2.volume_fractions, mat3.volume_fractions)

        assert_fractions_equal(mat1.mass_fractions, mat2.mass_fractions)
        assert_fractions_equal(mat1.mass_fractions, mat3.mass_fractions)
        assert_fractions_equal(mat2.mass_fractions, mat3.mass_fractions)

        numpy.testing.assert_allclose(mat1.density, mat2.density)
        numpy.testing.assert_allclose(mat1.density, mat3.density)
        numpy.testing.assert_allclose(mat2.density, mat3.density)

        if not iscompound:
            numpy.testing.assert_allclose(mat1.molar_mass, mat2.molar_mass)
            numpy.testing.assert_allclose(mat1.molar_mass, mat3.molar_mass)
            numpy.testing.assert_allclose(mat2.molar_mass, mat3.molar_mass)


def assert_fractions_equal(fractions1, fractions2):
    assert set(fractions1.keys()) == set(fractions2.keys())
    for k in fractions1:
        numpy.testing.assert_allclose(fractions1[k], fractions2[k], err_msg=str(k))


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_element_cross_sections(backend):
    _set_backend(backend)
    mat = materials.Element("Fe")
    assert mat.cross_section(10).shape == (1,)
    assert mat.cross_section([10, 20]).shape == (2,)
    assert mat.transmission(10, 0.1).shape == (1,)
    assert mat.transmission([10, 20], 0.1).shape == (2,)


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_compound_cross_sections(backend):
    _set_backend(backend)
    mat = materials.Compound("Fe2O3", density=5.25)
    assert mat.cross_section(10).shape == (1,)
    assert mat.cross_section([10, 20]).shape == (2,)
    assert mat.transmission(10, 0.1).shape == (1,)
    assert mat.transmission([10, 20], 0.1).shape == (2,)


@pytest.mark.parametrize("backend", backend.MATERIAL_BACKENDS)
def test_mixture_cross_sections(backend):
    _set_backend(backend)
    c1 = materials.Compound("Fe2O3", density=5.25)
    c2 = materials.Compound("Al2O3", density=3)
    m1 = materials.Mixture({c1: 1, c2: 1}, kind="mole")
    mat = materials.Mixture({m1: 1, c2: 1, "Al": 1}, kind="mole")
    assert mat.cross_section(10).shape == (1,)
    assert mat.cross_section([10, 20]).shape == (2,)
    assert mat.transmission(10, 0.1).shape == (1,)
    assert mat.transmission([10, 20], 0.1).shape == (2,)

    mat = materials.Mixture({m1: 1, c2: 1, "Al": 1}, kind="volume")
    energies = [10, 20]
    t = mat.transmission(energies, 0.03)
    t1 = m1.transmission(energies, 0.01)
    t2 = c2.transmission(energies, 0.01)
    t3 = materials.Element("Al").transmission(energies, 0.01)
    numpy.testing.assert_allclose(t, t1 * t2 * t3)
