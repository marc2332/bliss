# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import fisx
from .helpers import get_cs_kind


_elementsInstance = fisx.Elements()
_elementsInstance.initializeAsPyMca()


def _cs_from_library(Z, energies, kind):
    symbol = element_atomicnumber_to_symbol(Z)
    csdict = _elementsInstance.getMassAttenuationCoefficients(symbol, energies)
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
        coh = csdict["coherent"]
        incoh = csdict["compton"]
        if isinstance(csdict["coherent"], list):
            coh = numpy.array(coh)
            incoh = numpy.array(incoh)
        return coh + incoh
    else:
        raise ValueError(f"{kind} not supported")


def element_atomicnumber_to_symbol(Z: int) -> str:
    return _elementsInstance.getElementNames()[Z - 1]


def element_symbol_to_atomicnumber(symbol: str) -> int:
    return _elementsInstance.getAtomicNumber(symbol)


def element_density(Z: int):
    return _elementsInstance.getDensity(element_atomicnumber_to_symbol(Z))


def atomic_weight(Z: int):
    return _elementsInstance.getAtomicMass(element_atomicnumber_to_symbol(Z))


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
