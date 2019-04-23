# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.physics.units import ur, units


@units(edge_energy="eV", energy="eV", result="angstrom ** -1")
def energy_to_wavevector(edge_energy, energy):
    """
    Calculate the photo electron wavevector k from:

    k =  sqrt(2*me*(energy − edge_energy))/hbar

    where hbar is the reduced planck constant and
          me is the electron mass
          edge_energy is the threshold energy defined as the binding
              energy of the photoelectron
    Args:
        edge_energy (float): energy (eV)
        energy (float): energy (eV)
    Returns:
        float: wavevector (angstrom ** -1)
    """
    energy_diff = energy - edge_energy
    sqroot = ((2.0 * ur("electron_mass")) * energy_diff) ** 0.5
    return sqroot / (1.0 * ur("hbar"))


@units(edge_energy="eV", k="angstrom ** -1", result="eV")
def wavevector_to_energy(edge_energy, k):
    """
    Calculate the photo electron wavevector k from:

    energy = (((k * hbar)**2)/2*me) + edge_energy

    where hbar is the reduced planck constant and
          me is the electron mass
          edge_energy is the threshold energy defined as the binding
              energy of the photoelectron
    Args:
        edge_energy (float): energy (eV)
        k (float): wavevector (angstrom ** -1)
    Returns:
        float: energy (eV)
    """
    khbar = k * (1.0 * ur("hbar"))
    result = (khbar * khbar) / (2.0 * ur("electron_mass"))
    return result + edge_energy
