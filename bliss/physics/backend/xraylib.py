# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import xraylib
import xraylib_np
from .helpers import get_cs_kind

NIST_NAME_MAPPING = {
    "water": "Water, Liquid",
    "air": "Air, Dry (near sea level)",
    "kapton": "Kapton Polyimide Film",
}
for name in xraylib.GetCompoundDataNISTList():
    NIST_NAME_MAPPING[name] = name
    NIST_NAME_MAPPING[name.replace(" ", "")] = name
    name2 = name.lower()
    NIST_NAME_MAPPING[name2] = name
    NIST_NAME_MAPPING[name2.replace(" ", "")] = name


element_atomicnumber_to_symbol = xraylib.AtomicNumberToSymbol

element_symbol_to_atomicnumber = xraylib.SymbolToAtomicNumber

element_density = xraylib.ElementDensity

atomic_weight = xraylib.AtomicWeight


def cross_section(Z, energies, kind):
    """Can be done in one xraylib call.

    :param sequence or num Z:
    :param sequence or num energies:
    :param str kind:
    :returns numpy.ndarray: nZ x nE
    """
    kind = get_cs_kind(kind)
    energies = numpy.atleast_1d(energies).astype(float)
    Z = numpy.atleast_1d(Z).astype(int)
    if kind == kind.TOTAL:
        return xraylib_np.CS_Total_Kissel(Z, energies)
    elif kind == kind.PHOTO:
        return xraylib_np.CS_Photo_Total(Z, energies)
    elif kind == kind.COHERENT:
        return xraylib_np.CS_Rayl(Z, energies)
    elif kind == kind.INCOHERENT:
        return xraylib_np.CS_Compt(Z, energies)
    elif kind == kind.SCATTER:
        return xraylib_np.CS_Rayl(Z, energies) + xraylib_np.CS_Compt(Z, energies)
    else:
        raise ValueError(f"{kind} not supported")


def compound_from_catalog(name):
    """
    :param str name:
    :returns dict:
    """
    try:
        name2 = NIST_NAME_MAPPING[name]
    except KeyError:
        raise ValueError(f"{repr(name)} was not found in the NIST compound database")
    result = xraylib.GetCompoundDataNISTByName(name2)
    mass_fractions = {
        element_atomicnumber_to_symbol(Z): wfrac
        for Z, wfrac in zip(result["Elements"], result["massFractions"])
    }
    return {
        "name": result["name"],
        "density": result["density"],
        "elemental_fractions": mass_fractions,
        "kind": "mass",
    }
