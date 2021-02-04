# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from PyMca5.PyMcaPhysics.xrf import Elements
from .helpers import get_cs_kind


def _cs_from_library(Z, energies, kind):
    symbol = element_atomicnumber_to_symbol(Z)
    csdict = Elements.getMaterialMassAttenuationCoefficients(symbol, 1, energies)
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
    cs = [_cs_from_library(Zi, energies, kind) for Zi in Z]
    return numpy.asarray(cs)


def compound_from_catalog(name):
    """
    :param str name:
    :returns dict:
    """
    raise ValueError(f"{repr(name)} was not found in the compound database")
