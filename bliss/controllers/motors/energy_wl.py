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
"""

from bliss.controllers.motor import CalcController; from bliss.common import event
import numpy


class energy_wl(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        self.axis_settings.add("dspace", float)

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)
        event.connect(axis, "dspace", self._calc_from_real)

    def calc_from_real(self, positions_dict):
        energy_axis = self._tagged["energy"][0]
        dspace = energy_axis.settings.get("dspace")
        if dspace is None:
            dspace = 3.13542
        # NB: lambda is a keyword.
        lamb = 2 * dspace * numpy.sin(numpy.radians(positions_dict["monoang"]))
        return {"energy": 12.3984 / lamb, "wavelength": lamb}

    def calc_to_real(self, positions_dict):
        energy_axis = self._tagged["energy"][0]
        dspace = energy_axis.settings.get("dspace")
        monoangle = numpy.degrees(numpy.arcsin(12.3984 / (positions_dict["energy"] * 2 * dspace)))
        return {"monoang": monoangle}
