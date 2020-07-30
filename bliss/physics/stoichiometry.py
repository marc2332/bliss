# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


def mole_to_mass_fractions(mole_fractions):
    """
    :param dict mole_fractions:
    :returns dict:
    """
    # xi = ni/total(nj) = mi/MMi / total(mj/MMj) = wi/MMi / total(wj/MMj)
    arr = [nfrac * item.molar_mass for item, nfrac in mole_fractions.items()]
    sarr = sum(arr)
    return {item: v / sarr for item, v in zip(mole_fractions, arr)}


def mass_to_mole_fractions(mass_fractions):
    """
    :param dict mass_fractions:
    :returns dict:
    """
    # wi = mi/total(mj) = ni*MMi / total(nj*MMj) = xi*MMi / total(xj*MMj)
    arr = [wfrac / item.molar_mass for item, wfrac in mass_fractions.items()]
    sarr = sum(arr)
    return {item: v / sarr for item, v in zip(mass_fractions, arr)}


def mass_to_volume_fractions(mass_fractions):
    """
    :param dict mass_fractions:
    :returns dict:
    """
    # vi = Vi/total(Vj) = mi/rhoi(Vi) / total(mj/rhoj(Vj)) = wi/rhoi(Vi) / total(wj/rhoj(Vj))
    arr = [wfrac / item.density for item, wfrac in mass_fractions.items()]
    sarr = sum(arr)
    return {item: v / sarr for item, v in zip(mass_fractions, arr)}


def volume_to_mass_fractions(volume_fractions):
    """
    :param dict volume_fractions:
    :returns dict:
    """
    # wi = mi/total(mj) = vi*rhoi(Vi) / total(vj*rhoi(Vj))
    arr = [vfrac * item.density for item, vfrac in volume_fractions.items()]
    sarr = sum(arr)
    return {item: v / sarr for item, v in zip(volume_fractions, arr)}


def volume_to_mole_fractions(volume_fractions):
    """
    :param dict volume_fractions:
    :returns dict:
    """
    arr = [
        vfrac * item.density / item.molar_mass
        for item, vfrac in volume_fractions.items()
    ]
    sarr = sum(arr)
    return {item: v / sarr for item, v in zip(volume_fractions, arr)}


def mole_to_volume_fractions(mole_fractions):
    """
    :param dict mole_fractions:
    :returns dict:
    """
    arr = [
        nfrac * item.molar_mass / item.density for item, nfrac in mole_fractions.items()
    ]
    sarr = sum(arr)
    return {item: v / sarr for item, v in zip(mole_fractions, arr)}


def density_from_volume_fractions(volume_fractions):
    """
    :param dict volmune_fractions:
    :returns num:
    """
    # rho(V) = total(mi)/V = total(vi*rhoi(Vi))
    return sum(vfrac * item.density for item, vfrac in volume_fractions.items())


def density_from_mass_fractions(mass_fractions):
    """
    :param dict mass_fractions:
    :returns num:
    """
    # rho(V) = total(mi)/V = total(vi*rhoi(Vi)) = total(wi / total(wj/rhoj(Vj))) = 1/total(wj/rhoj(Vj))
    return 1 / sum(wfrac / item.density for item, wfrac in mass_fractions.items())


def density_from_mole_fractions(mole_fractions):
    """
    :param dict mole_fractions:
    :returns num:
    """
    num = 0
    denom = 0
    for item, nfrac in mole_fractions.items():
        tmp = nfrac * item.molar_mass
        num += tmp
        denom += tmp / item.density
    return num / denom


def molarmass_from_volume_fractions(volume_fractions):
    """
    :param dict volume_fractions:
    :returns num:
    """
    num = 0
    denom = 0
    for item, vfrac in volume_fractions.items():
        tmp = vfrac * item.density
        num += tmp
        denom += tmp / item.molar_mass
    return num / denom


def molarmass_from_mass_fractions(mass_fractions):
    """
    :param dict mass_fractions:
    :returns num:
    """
    # MM = M/n = total(mi)/total(mi/MMi) = total(wi)/total(wi/MMi) = 1/total(wi/MMi)
    return 1 / sum(wfrac / item.molar_mass for item, wfrac in mass_fractions.items())


def molarmass_from_mole_fractions(mole_fractions):
    """
    :param dict mole_fractions:
    :returns num:
    """
    return sum(nfrac * item.molar_mass for item, nfrac in mole_fractions.items())
