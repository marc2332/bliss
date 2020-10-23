# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from scipy.interpolate import interp1d
from PyMca5.PyMcaPhysics.xrf import Elements
from .helpers import get_cs_kind

_cs_catalog = {}


def _get_from_cs_catalog(Z, kind):
    symbol = element_atomicnumber_to_symbol(Z)
    csdict = _cs_catalog.get(symbol, {})
    if not csdict:
        adict = Elements.getMaterialMassAttenuationCoefficients(symbol, 1)
        x = adict.pop("energy")
        for key, y in adict.items():
            csdict[key] = interp1d(
                x, y, kind="linear", bounds_error=False, fill_value=numpy.nan
            )
    if kind == kind.TOTAL:
        return csdict["total"]
    elif kind == kind.PHOTO:
        return csdict["photo"]
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


def element_atomicnumber_to_symbol(Z: int) -> str:
    return Elements.ElementList[Z - 1]


def element_symbol_to_atomicnumber(symbol: str) -> int:
    return Elements.Element[symbol.capitalize()]["Z"]


def element_density(Z: int):
    symbol = element_atomicnumber_to_symbol(Z)
    return Elements.Element[symbol]["density"]


def atomic_weight(Z: int):
    symbol = element_atomicnumber_to_symbol(Z)
    return Elements.Element[symbol]["mass"]


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
