# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from scipy.interpolate import interp1d
import fisx
import mendeleev
from .helpers import get_cs_kind


_elementsInstance = fisx.Elements()
_cs_catalog = {}
_element_catalog = {}


def _get_from_cs_catalog(Z, kind):
    symbol = element_atomicnumber_to_symbol(Z)
    csdict = _cs_catalog.get(symbol, {})
    if not csdict:
        adict = _elementsInstance.getMassAttenuationCoefficients(symbol)
        x = adict.pop("energy")
        for key, y in adict.items():
            csdict[key] = interp1d(
                x, y, kind="linear", bounds_error=False, fill_value=numpy.nan
            )
    if kind == kind.TOTAL:
        return csdict["total"]
    elif kind == kind.PHOTO:
        return csdict["photoelectric"]
    elif kind == kind.COHERENT:
        return csdict["coherent"]
    elif kind == kind.INCOHERENT:
        return csdict["compton"]
    elif kind == kind.PAIR:
        return csdict["pair"]
    elif kind == kind.SCATTER:
        f1, f2 = csdict["coherent"], csdict["compton"]

        def func(energies):
            return f1(energies) + f2(energies)

        return func
    else:
        raise ValueError(f"{kind} not supported")


def _get_from_element_catalog(symbol_or_z):
    if not isinstance(symbol_or_z, str):
        symbol_or_z = int(symbol_or_z)
    e = _element_catalog.get(symbol_or_z)
    if e is None:
        e = mendeleev.element(symbol_or_z)
        _element_catalog[symbol_or_z] = e
        _element_catalog[e.symbol] = e
        _element_catalog[e.atomic_number] = e
    return e


def element_atomicnumber_to_symbol(Z: int) -> str:
    return _get_from_element_catalog(Z).symbol


def element_symbol_to_atomicnumber(symbol: str) -> int:
    return _get_from_element_catalog(symbol).atomic_number


def element_density(Z: int):
    return _get_from_element_catalog(Z).density


def atomic_weight(Z: int):
    return _get_from_element_catalog(Z).atomic_weight


def cross_section(Z, energies, kind):
    """Cross section functions are cached.

    :param sequence or num Z:
    :param sequence or num energies:
    :param str kind:
    :returns numpy.ndarray: nZ x nE
    """
    kind = get_cs_kind(kind)
    energies = numpy.atleast_1d(energies).astype(float)
    Z = numpy.atleast_1d(Z).astype(int)
    cs = [_get_from_cs_catalog(Zi, kind)(energies) for Zi in Z]
    return numpy.asarray(cs)


def compound_from_catalog(name):
    """
    :param str name:
    :returns dict:
    """
    raise ValueError(f"{repr(name)} was not found in the compound database")
