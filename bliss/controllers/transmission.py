# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Get/Set transmission factor as function of the filters, mounted on a
ESRF standard monochromatic attenuator and the energy (fixed or tunable).
It may not be possible to set the exact factor required.

yml configuration example:
name: transmission
class: transmission
matt: $matt
energy: $energy (or energy: 12.7)
datafile: "/users/blissadm/local/beamline_control/configuration/misc/transmission.dat"
"""

from bliss.controllers._transmission_calc import (
    get_attenuation,
    get_transmission_factor,
)


class Energy:
    def __init__(self, energy):
        self.__energy = energy
        if isinstance(energy, float):
            self.tunable = False
        else:
            self.tunable = True

    def read(self):
        if self.tunable:
            return self.__energy.position
        else:
            return self.__energy


class transmission:
    def __init__(self, name, config):

        energy = config.get("energy")
        if energy:
            self.energy = Energy(energy)
        self.datafile = config.get("datafile")

        self.__matt = config.get("matt")

    def set(self, transm):
        """ Set the transmission
        Args:
            transm (float): transmission factor (0-100)
        Raises:
            RuntimeError: wrong energy or not possible attenuators combination
        """
        en = self.energy.read()
        if en <= 0:
            raise RuntimeError("Wrong energy input %g" % en)

        transm, vals = get_attenuation(en, transm, self.datafile)
        if not vals:
            raise RuntimeError("No attenuators combination found for energy %g" % en)
        value = 0
        if -1 not in vals:
            for i in vals:
                value += 1 << i
        self.__matt.mattstatus_set(value)
        self.transmission_factor = transm

    def get(self):
        """ Read the current transmission factor
        Returns:
            transmission_factor (float): current transmission factor
        """
        en = self.energy.read()
        if en <= 0:
            raise RuntimeError("Wrong energy input %g" % en)

        _matt = self.__matt._status_read()

        if _matt:
            self.transmission_factor = get_transmission_factor(en, _matt, self.datafile)
        else:
            self.transmission_factor = 100.
        return self.transmission_factor
