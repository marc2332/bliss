# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Energy/wavelength Bliss controller
Calculate energy [keV] / wavelength [Angstrom] from angle or
angle [deg] from energy [keV], using the Bragg's law

monoang: alias for the real monochromator motor
energy: energy calculated axis alias
wavelength: wavelength calculated axis alias
dspace: monochromator crystal d-spacing

Antonia Beteva ESRF BCU

Example yml:-

    class: energy_wl
    axes:
        -
            name: $mono
            tags: real monoang
        -
            name: energy
            tags: energy
            dspace: 3.1356
            low_limit: 7000
            high_limit: 17000
            unit: eV  (or keV)
        -
            name: lambda
            description: monochromtor wavelength
            tags: wavelength
"""

from bliss.controllers.motor import CalcController
from bliss.common import event
import numpy


class energy_wl(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self.no_offset = self.config.get("no_offset", bool, True)
        self.axis_settings.add("dspace", float)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        axis.no_offset = self.no_offset
        event.connect(axis, "dspace", self._calc_from_real)
        axis.unit = axis.config.get("unit", str, default="keV")

    def calc_from_real(self, positions_dict):
        energy_axis = self._tagged["energy"][0]
        dspace = energy_axis.settings.get("dspace")
        if dspace is None:
            dspace = 3.13542
        # NB: lambda is a keyword.
        lamb = 2 * dspace * numpy.sin(numpy.radians(positions_dict["monoang"]))
        energy = 12.3984 / lamb
        if energy_axis.unit == "eV":
            energy *= 1000.0
        return {"energy": energy, "wavelength": lamb}

    def calc_to_real(self, positions_dict):
        energy_axis = self._tagged["energy"][0]
        dspace = energy_axis.settings.get("dspace")
        evs = positions_dict["energy"]
        if energy_axis.unit == "eV":
            monoangle = numpy.degrees(
                numpy.arcsin(12.3984 * 1000.0 / (evs * 2 * dspace))
            )
        else:
            monoangle = numpy.degrees(numpy.arcsin(12.3984 / (evs * 2 * dspace)))
        return {"monoang": monoangle}
