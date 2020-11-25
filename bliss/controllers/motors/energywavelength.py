# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Energy/wavelength Bliss controller
Calculate energy [keV] / wavelength [Angstrom] from angle [deg] or
angle [deg] from energy [keV].
Either Bragg's law or linear interpolation in a look-up table (LUT)
is used for calculating.

Parameters:

either:
* monoang: alias for the real monochromator motor
* energy: energy calculated axis alias
* wavelength: wavelength calculated axis alias
* dspace: monochromator crystal d-spacing

or:
* lut: Loouk-up Table (full path)

Antonia Beteva ESRF BCU

Example yml:

    class: EnergyWavelength
    lut: /users/blissadm/local/beamline_configuration/misc/energy.lut
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


"""
CYRIL [4]: e_mono
  Out [4]: AXIS:
                name (R): e_mono
                unit (R): keV
                offset (R): 0.00000
                backlash (R): 0.00000
                sign (R): 1
                steps_per_unit (R): 1.00
                tolerance (R) (to check pos. before a move): 0.0001
                limits (RW):    Low: -inf High: inf    (config Low: -inf High: inf)
                dial (RW): 10.00235
                position (RW): 10.00235
                state (R): READY (Axis is READY)
                acceleration: None
                velocity: None

           ENERGY-WAVELENGTH CALCULATION MOTOR:
                    energy axis: e_mono (  10.00235 keV)
                wavelength axis: wl_mono (   1.23955 Å)
                      mono axis: mono (  11.40000 deg)
                         dspace: 3.1356

           ENCODER:
                None

"""


import numpy
from bliss.controllers.motor import CalcController
from bliss.common import event


class EnergyWavelength(CalcController):
    """ Calculation controller for energy and wavelength.
    """

    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self.no_offset = self.config.get("no_offset", bool, True)
        self.e_factor = 1
        self.m_factor = 1
        self.energy_array = None
        self.mono_array = None
        self.lut = self.config.get("lut", default="")
        if self.lut:
            self.energy_array, self.mono_array = self._load_en_table(self.lut)
        else:
            self.axis_settings.add("dspace", float)

    def initialize_axis(self, axis):
        """ Initialize the axis and create dspace settings.
        Args:
            axis (Axis): Motor axis.
        """
        CalcController.initialize_axis(self, axis)
        axis.no_offset = self.no_offset
        if not self.energy_array:
            event.connect(axis, "dspace", self._calc_from_real)
        axis._unit = axis.config.get("unit", str, default="keV")

    def close(self):
        """ ???
        """
        for pseudo_axis in self.pseudos:
            event.disconnect(pseudo_axis, "dspace", self._calc_from_real)
        super().close()

    def _load_en_table(self, filename):
        """Load the look-up table.
           As numpy only interpolates increasing arrays, we may need to covert
           any of the return array, by multiplying them with -1. For this
           reason we also set two factors (for energy and angle).
        Args:
            filename (str): full path.
        Returns:
            e_a (array): Array of the energues (increasing values).
            m_a (array): Array of the angles (increasing values).
        """

        array = []
        with open(filename) as _fd:
            for line in _fd:
                array.append(list(map(float, line.split())))
        if not array:
            raise RuntimeError("Energy LUT file format error")

        if array[0][0] > 999:
            # energy id in eV, we want it in keV
            e_a = [c[0] / 1000.0 for c in array]
        else:
            e_a = [c[0] for c in array]
        m_a = [c[1] for c in array]

        # this is a way to make the arrays increasing
        if sorted(e_a) != e_a:
            self.e_factor = -1
            e_a = [c * -1 for c in e_a]
        if sorted(m_a) != m_a:
            self.m_factor = -1
            m_a = [c * -1 for c in m_a]

        return e_a, m_a

    def __info__(self):
        """ Return info about CalcController.
        """
        info_str = "\nENERGY-WAVELENGTH CALCULATION MOTOR:\n"
        _ene_axis = self._tagged["energy"][0]
        _wl_axis = self._tagged["wavelength"][0]
        _mono_axis = self._tagged["monoang"][0]

        info_str += (
            f"         energy axis: {_ene_axis.name} ({_ene_axis.position:10.5f} keV)\n"
        )
        info_str += (
            f"     wavelength axis: {_wl_axis.name} ({_wl_axis.position:10.5f} Å)\n"
        )
        info_str += f"           mono axis: {_mono_axis.name} ({_mono_axis.position:10.5f} deg)\n"

        if self.lut:
            info_str += "     Use LUT: \n"
            info_str += "     \n"
        else:
            _dspace = _ene_axis.settings.get("dspace")
            info_str += f"              dspace: {_dspace}\n"

        return info_str

    def get_axis_info(self, axis):
        info_str = "\n"
        return info_str

    def calc_from_real(self, real_positions):
        """ Calculate the energy [ev] or [keV] and wavelength [Angstrom].
        Args:
            real_positions (dict): dictionary containing the mono angle.
        Returns:
            (dict): Dictionary containing energy and wavelength.
        """

        energy_axis = self._tagged["energy"][0]
        angle = self.m_factor * real_positions["monoang"]
        if self.mono_array:
            energy = self.e_factor * numpy.interp(
                angle, self.mono_array, self.energy_array
            )
            lamb = 12.3984 / energy
        else:
            dspace = energy_axis.settings.get("dspace") or 3.13542
            # NB: lambda is a keyword.
            lamb = 2 * dspace * numpy.sin(numpy.radians(angle))
            energy = 12.3984 / lamb
        try:
            if energy_axis.unit == "eV":
                energy *= 1000
        except AttributeError:
            pass
        return {"energy": energy, "wavelength": lamb}

    def calc_to_real(self, positions_dict):
        """ Calculate the mono angle [deg].
        Args:
            positions_dict (dict): dictionary containing the energy.
        Returns:
            (dict): Dictionary containing the mono angle.
        """
        energy_pos = numpy.array(positions_dict["energy"])
        wavelength = numpy.array(positions_dict["wavelength"])
        egy = numpy.zeros(wavelength.shape)
        egy[energy_pos < 2] = self.e_factor * 12.3984 // wavelength[energy_pos < 2]
        egy[energy_pos >= 2] = self.e_factor * energy_pos[energy_pos >= 2]

        energy_axis = self._tagged["energy"][0]
        try:
            if energy_axis.unit == "eV":
                egy /= 1000.0
        except AttributeError:
            pass

        if self.mono_array:
            monoangle = self.m_factor * numpy.interp(
                egy, self.energy_array, self.mono_array
            )
        else:
            dspace = energy_axis.settings.get("dspace") or 3.13542

            monoangle = numpy.degrees(numpy.arcsin(12.3984 / (egy * 2 * dspace)))
        return {"monoang": monoangle}
