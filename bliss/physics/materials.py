# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Interaction between X-rays and matter

    Defining materials:
        # Pure elements
        material = Element(26)
        material = Element("Al")

        # Compounds
        material = Compound("Fe2O3", density=5.25)
        material = Compound({"Fe":0.6, "O":0.4}, kind="mass", density=5.25)
        material = Compound("water")

        # Mixtures of pure elements, compounds or other mixtures
        comp1 = Compound(...)
        comp2 = Compound(...)
        mix1 = Mixture(...)
        material = Mixture({comp1:2, comp2:3, mix1:3}, kind="volume")
    
    Material properties:
        molar_mass: g/mol
        density: g/cm^3
        equivalents:
        mole_fractions:
        mass_fractions:
        volume_fraction:
    
    Interaction with X-rays:
        cross_section(energies, kind="total"): cm^2/g
        linear_attenuation(energies): mass_attenuation*density (1/cm)
        absorbance(energies, thickness): linear_attenuation*thickness
        transmission(energies, thickness): exp(-absorbance)
"""

from typing import Union
import operator
from numbers import Integral
from collections.abc import Mapping
import pyparsing as pp
import numpy
from bliss.physics import stoichiometry
from bliss.physics.backend import MaterialBackend


class AbstractMaterial(MaterialBackend):
    def __hash__(self):
        return hash(self._cmp_key)

    def __str__(self):
        return repr(self)

    @property
    def _cmp_key(self):
        raise NotImplementedError

    @property
    def _sort_key(self):
        return self._cmp_key

    def _cmp(self, other, op):
        if op in (operator.eq, operator.ne):
            if isinstance(other, AbstractMaterial):
                return op(self._cmp_key, other._cmp_key)
            else:
                return op(self._cmp_key, other)
        else:
            if isinstance(other, AbstractMaterial):
                return op(self._sort_key, other._sort_key)
            else:
                return op(self._sort_key, other)

    def __eq__(self, other):
        return self._cmp(other, operator.eq)

    def __ne__(self, other):
        return self._cmp(other, operator.ne)

    def __lt__(self, other):
        return self._cmp(other, operator.lt)

    def __le__(self, other):
        return self._cmp(other, operator.le)

    def __gt__(self, other):
        return self._cmp(other, operator.gt)

    def __ge__(self, other):
        return self._cmp(other, operator.ge)

    @property
    def density(self):
        """(g/cm^3)"""
        raise NotImplementedError

    @property
    def molar_mass(self):
        """Mass of 1 mole of units (g/mol)"""
        raise NotImplementedError

    @property
    def mass_fractions(self):
        """Unit dict of mass fractions"""
        raise NotImplementedError

    @property
    def mole_fractions(self):
        """Unit dict of mole fractions"""
        raise NotImplementedError

    @property
    def equivalents(self):
        """Unit dict of equivalents"""
        raise NotImplementedError

    @property
    def elemental_mass_fractions(self):
        """Element dict of mass fractions"""
        raise NotImplementedError

    @property
    def elemental_mole_fractions(self):
        """Element dict of mole fractions"""
        raise NotImplementedError

    @property
    def elemental_equivalents(self):
        """Element dict of equivalents"""
        raise NotImplementedError

    @property
    def elements(self):
        """Set of elements"""
        raise NotImplementedError

    def cross_section(self, energies, kind=None, cache=None):
        """
        :param sequence or num energies: keV
        :param str kind: total (default), coherent, incoherent, ...
        :param dict cache: cross-section cache for optimization
        :returns numpy.ndarray: cm^2/g
        """
        if cache is None:
            # Cache the cross-sections of all elements
            elements = self.elements
            Z = [el.Z for el in elements]
            if kind is None:
                kind = "total"
            arr = self.get_backend().cross_section(Z, energies, kind)
            cache = {el: cs for el, cs in zip(elements, arr)}
        cs = cache.get(self)
        if cs is None:
            # Calculate and cash the cross-section
            cs = 0
            for item, wfrac in self.mass_fractions.items():
                cs += wfrac * item.cross_section(energies, kind=kind, cache=cache)
            cache[self] = cs
        return cs

    def linear_attenuation(self, energies):
        """
        :param sequence or num energies: keV
        :returns numpy.ndarray: 1/cm
        """
        return self.cross_section(energies, kind="mass_attenuation") * self.density

    def absorbance(self, energies, thickness):
        """
        :param sequence or num energies: keV
        :param num thickness:
        :returns numpy.ndarray:
        """
        return self.linear_attenuation(energies) * thickness

    def transmission(self, energies, thickness):
        """
        :param sequence or num energies: keV
        :param num thickness:
        :returns numpy.ndarray:
        """
        return numpy.exp(-self.absorbance(energies, thickness))

    def density_from_linear_attenuation(self, energies, linear_attenuation):
        """
        :param sequence or num energies: keV
        :param sequence or num linear_attenuation: 1/cm
        """
        linear_attenuation = numpy.asarray(linear_attenuation)
        cs = self.cross_section(energies, kind="mass_attenuation")
        self.density = numpy.median(linear_attenuation / cs)

    def density_from_absorbance(self, energies, absorbance, thickness):
        """
        :param sequence or num energies: keV
        :param sequence or num absorbance:
        :param sequence or num thickness: cm
        """
        absorbance = numpy.asarray(absorbance)
        thickness = numpy.asarray(thickness)
        self.density_from_linear_attenuation(energies, absorbance / thickness)

    def density_from_transmission(self, energies, transmission, thickness):
        """
        :param sequence or num energies: keV
        :param sequence or num transmission:
        :param sequence or num thickness: cm
        """
        self.density_from_absorbance(energies, -numpy.log(transmission), thickness)


class Element(AbstractMaterial):
    def __init__(self, element: Union[str, Integral], density=None):
        if isinstance(element, str):
            if element.isdigit():
                self._Z = int(element)
                self._symbol = self.get_backend().element_atomicnumber_to_symbol(
                    self._Z
                )
            else:
                self._symbol = element.capitalize()
                self._Z = self.get_backend().element_symbol_to_atomicnumber(
                    self._symbol
                )
        elif isinstance(element, Integral):
            self._Z = element
            self._symbol = self.get_backend().element_atomicnumber_to_symbol(self._Z)
        else:
            raise TypeError("element")
        self.density = density
        self._atomic_weight = self.get_backend().atomic_weight(self._Z)

    def __repr__(self):
        return self._symbol

    @property
    def _cmp_key(self):
        return self._symbol

    @property
    def _sort_key(self):
        return self._Z

    @property
    def atomic_number(self):
        return self._Z

    @property
    def Z(self):
        return self._Z

    @property
    def symbol(self):
        return self._symbol

    @property
    def atomic_weight(self):
        """Weighted average of the atomic masses of the naturally
        occurring isotopes (Dalton)."""
        return self._atomic_weight

    @property
    def density(self):
        """(g/cm^3)"""
        return self._density

    @density.setter
    def density(self, value):
        """(g/cm^3)"""
        if value is None:
            value = self.get_backend().element_density(self.Z)
        self._density = value

    @property
    def molar_mass(self):
        """Mass of one mole of atoms with natural isotopic ratio's (g/mol).
        """
        # 2019 redefinition of the SI base units:
        #
        # Na: 6.02214076e23 (Avogadro number)
        # 1 mole: Na atoms
        # 1 Da: 1⁄12 of the mass of an atom of 12C in its ground state
        # 1 mole of 12C = 0.99999999965(30)g
        #
        # 1 Da = 0.99999999965(30)/Na g
        # molar mass (g/mol) = atomic weight (Da) * Na
        return self.atomic_weight  # *0.99999999965

    @property
    def mass_fractions(self):
        return {self: 1}

    @property
    def mole_fractions(self):
        return {self: 1}

    @property
    def equivalents(self):
        return {self: 1}

    @property
    def elemental_mass_fractions(self):
        return {self: 1}

    @property
    def elemental_mole_fractions(self):
        return {self: 1}

    @property
    def elemental_equivalents(self):
        return {self: 1}

    @property
    def elements(self):
        return {self}

    def cross_section(self, energies, kind=None, cache=None):
        """
        :param sequence or num energies: keV
        :param str kind: total (default), coherent, incoherent, ...
        :param dict cache: cross-section cache for optimization
        :returns numpy.ndarray:
        """
        if kind is None:
            kind = "total"
        if cache is None:
            return self.get_backend().cross_section(self._Z, energies, kind)[0]
        cs = cache.get(self)
        if cs is None:
            # Calculate and cash the cross-section
            cache[self] = cs = self.get_backend().cross_section(
                self._Z, energies, kind
            )[0]
        else:
            return cs


class AbstractCompositeMaterial(AbstractMaterial):
    def __init__(self, items: Mapping, kind=None, name=None):
        self._name = name
        self.set_items(items, kind=kind)

    def __repr__(self):
        if self._name:
            return self._name
        else:
            lst = []
            for item, f in self.equivalents.items():
                if f == 1:
                    s = str(item)
                elif f == 0:
                    s = ""
                elif isinstance(item, Element):
                    s = f"{item}{f}"
                else:
                    s = f"({item}){f}"
                lst.append(s)
            return "".join(lst)

    @property
    def _cmp_key(self):
        if self._name:
            return self._name
        else:
            return tuple(sorted(self.elemental_equivalents.items())) + (self.density,)

    def set_items(self, items, kind=None):
        if kind not in ("mass", "mole", "volume"):
            raise ValueError("kind must be 'mass' or 'mole'")
        self._kind = kind
        self._items = {}
        self._denom = 0
        for item, n in items.items():
            self._items.setdefault(item, 0)
            self._items[item] += n
            self._denom += n

    @property
    def fractions(self):
        return {item: f / self._denom for item, f in self._items.items()}

    @property
    def mass_fractions(self):
        if self._kind == "mass":
            return self.fractions
        elif self._kind == "volume":
            return stoichiometry.volume_to_mass_fractions(self.fractions)
        else:
            return stoichiometry.mole_to_mass_fractions(self.fractions)

    @mass_fractions.setter
    def mass_fractions(self, fractions):
        self.set_items(fractions, kind="mass")

    @property
    def volume_fractions(self):
        if self._kind == "volume":
            return self.fractions
        elif self._kind == "mole":
            return stoichiometry.mole_to_volume_fractions(self.fractions)
        else:
            return stoichiometry.mass_to_volume_fractions(self.fractions)

    @volume_fractions.setter
    def volume_fractions(self, fractions):
        self.set_items(fractions, kind="volume")

    @property
    def mole_fractions(self):
        if self._kind == "mole":
            return self.fractions
        elif self._kind == "volume":
            return stoichiometry.volume_to_mole_fractions(self.fractions)
        else:
            return stoichiometry.mass_to_mole_fractions(self.fractions)

    @mole_fractions.setter
    def mole_fractions(self, fractions):
        self.set_items(fractions, kind="mole")

    @property
    def equivalents(self):
        if self._kind == "mole":
            return dict(self._items)
        else:
            return self.mole_fractions

    @equivalents.setter
    def equivalents(self, equivalents):
        self.set_items(equivalents, kind="mole")

    @property
    def elemental_mass_fractions(self):
        return stoichiometry.mole_to_mass_fractions(self.elemental_mole_fractions)

    @property
    def elemental_mole_fractions(self):
        result = self.elemental_equivalents
        vtot = sum(result.values())
        return {item: v / vtot for item, v in result.items()}

    @property
    def elemental_equivalents(self):
        result = {}
        for item, v in self.equivalents.items():
            for item2, v2 in item.elemental_equivalents.items():
                result.setdefault(item2, 0)
                result[item2] += v2 * v
        return result

    @property
    def elements(self):
        return {e for item in self.equivalents for e in item.elements}

    def simplify(self, name=None):
        equivalents = self.elemental_equivalents
        if len(equivalents) == 1:
            return Element(next(iter(equivalents.keys())).symbol, density=self.density)
        else:
            return Compound(equivalents, name=name, density=self.density, kind="mole")


class FormulaParser:
    """Parse chemical formulae as a dictionary of element equivalents
    """

    def __init__(self):
        lpar = pp.Literal("(").suppress()
        rpar = pp.Literal(")").suppress()

        element = pp.Combine(
            pp.Word(pp.srange("[A-Z]"), exact=1)
            + pp.Optional(pp.Word(pp.srange("[a-z]"), max=1))
        )
        integer = pp.Word(pp.nums)
        point = pp.Literal(".")
        fnumber = pp.Combine(
            integer + pp.Optional(point + pp.Optional(integer))
        ) | pp.Combine(point + integer)

        self.formula = pp.Forward()
        atom = element | pp.Group(lpar + self.formula + rpar)
        self.formula << pp.OneOrMore(pp.Group(atom + pp.Optional(fnumber, default="1")))
        self.elements = {}

    def parseresult(self, result, mult):
        """
        :param pp.ParseResults or str result: pyparsing result
        :param num mult: multiplier
        """
        if isinstance(result, pp.ParseResults):
            if isinstance(result[-1], str):
                if result[-1].isdigit():
                    mult *= int(result[-1])
                elif not result[-1].isalpha():
                    mult *= float(result[-1])
            for r in result:
                self.parseresult(r, mult)
        elif result[-1].isalpha():
            if result in self.elements:
                self.elements[result] += mult
            else:
                self.elements[result] = mult

    def eval(self, formula: str) -> dict:
        """
        :param str formula:
        :returns dict: element -> equivalent
        """
        self.elements = {}
        result = self.formula.parseString(formula)
        self.parseresult(result, 1)
        return self.elements


class Compound(AbstractCompositeMaterial):

    PARSER = FormulaParser()

    def __init__(
        self, composition: Union[str, Mapping], name=None, density=None, kind=None
    ):
        if isinstance(composition, str):
            try:
                composition = self.get_backend().compound_from_catalog(composition)
            except ValueError:
                if kind is not None:
                    raise ValueError("Cannot specify kind when providing a formula")
                kind = "mole"
                composition = self.PARSER.eval(composition)
            else:
                kind = composition["kind"]
                if density is None:
                    density = composition["density"]
                if not name:
                    name = composition["name"]
                composition = composition["elemental_fractions"]
        if isinstance(composition, Mapping):
            items = {
                e if isinstance(e, Element) else Element(e): n
                for e, n in composition.items()
            }
        else:
            raise TypeError("composition")
        super().__init__(items, name=name, kind=kind)
        self.density = density

    @property
    def density(self):
        """(g/cm^3)"""
        return self._density

    @density.setter
    def density(self, value):
        """(g/cm^3)"""
        if value is None:
            if len(self._items) == 1:
                value = next(iter(self._items.keys())).density
        self._density = value

    @property
    def molar_mass(self):
        """Total molar mass (g/mol)"""
        return sum(
            nfrac * element.molar_mass for element, nfrac in self.equivalents.items()
        )

    @classmethod
    def from_catalog(cls, name: str):
        adict = cls.get_backend().compound_from_catalog(name)
        composition = adict.pop("elemental_fractions")
        return Compound(composition, **adict)

    @classmethod
    def factory(cls, name_or_formula: str, density=None):
        """
        :param str name_or_formula:
        :param num density:
        """
        try:
            c = cls.from_catalog(name_or_formula)
        except ValueError:
            c = Compound(name_or_formula)
        if density is not None:
            c.density = density
        return c


class Mixture(AbstractCompositeMaterial):
    def __init__(self, composition: Mapping, name=None, kind=None):
        if isinstance(composition, Mapping):
            items = {
                e if isinstance(e, AbstractMaterial) else Compound(e): n
                for e, n in composition.items()
            }
        else:
            raise TypeError("fractions")
        super().__init__(items, name=name, kind=kind)

    @property
    def molar_mass(self):
        """Average molar mass of the compounds (g/mol)"""
        if self._kind == "mole":
            return stoichiometry.molarmass_from_mole_fractions(self.fractions)
        elif self._kind == "volume":
            return stoichiometry.molarmass_from_volume_fractions(self.fractions)
        else:
            return stoichiometry.molarmass_from_mass_fractions(self.fractions)

    @property
    def density(self):
        """(g/cm^3)"""
        if self._kind == "mole":
            return stoichiometry.density_from_mole_fractions(self.fractions)
        elif self._kind == "volume":
            return stoichiometry.density_from_volume_fractions(self.fractions)
        else:
            return stoichiometry.density_from_mass_fractions(self.fractions)
