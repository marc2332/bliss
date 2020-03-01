# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Test spectroscopy"""

from pytest import approx
from functools import partial
from bliss.physics.units import ur
from bliss.physics.spectroscopy import energy_to_wavevector
from bliss.physics.spectroscopy import wavevector_to_energy

approx = partial(approx, rel=1e-11, abs=0.)

# scipy constants have changed, see: https://github.com/scipy/scipy/commit/f166e3a7140d72dbd7cd718fbf65c53ba4a3a961#diff-0680be3eaa6e6ae60d2e2118fc49b13e


def test_wave_vector():
    """
    ???
    """
    edge_energy = 7112  #  Fe K-edge in eV.
    energy = 7124.5
    wavevector = 1.8113131410923873

    q_edge_energy = edge_energy * ur("eV")
    ev = energy * ur("eV")
    kev = (energy / 1000.) * ur("keV")
    q_wavevector = 1.8113131410923873 * ur("angstrom ** -1")

    k = energy_to_wavevector(edge_energy, energy)
    assert k == approx(wavevector)

    k = energy_to_wavevector(q_edge_energy, ev)
    assert k.magnitude == approx(wavevector)

    k = energy_to_wavevector(q_edge_energy, kev)
    assert k.magnitude == approx(wavevector)

    ecalc = wavevector_to_energy(edge_energy, wavevector)
    assert ecalc == approx(energy)

    ecalc = wavevector_to_energy(q_edge_energy, q_wavevector)
    assert ecalc.magnitude == approx(energy)
