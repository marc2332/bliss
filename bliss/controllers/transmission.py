# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Get/Set transmission factor as function of the filters, mounted on a
ESRF standard monochromatic attenuator aznd the energy (fixed or tunable).

yml configuration example:
name: transmission
class: transmission
matt: $matt
energy: $energy (or energy: 12.7)
datafile: "/users/blissadm/local/beamline_control/configuration/misc/transmission.dat"
"""

from bliss.controllers import _transmission_calc


class Energy:
    def __init__(self, energy):
        self.__energy = energy
        if isinstance(energy, float):
            self.tunable = False
        else:
            self.tunable = True

    def read(self):
        if self.tunable:
            return self.__energy.position()
        else:
            return self.__energy


class transmission:
    def __init__(self, name, config):
        try:
            # fixed energy
            self.energy = Energy(float(config["energy"]))
        except:
            # tunable energy: energy motor is expected
            self.energy = Energy(config["energy"])
        try:
            self.datafile = config["datafile"]
        except:
            self.datafile = None

        self.__matt = config["matt"]

    def set(self, transm):
        vals = []
        value = 0
        en = self.energy.read()
        if en <= 0:
            raise RuntimeError("Wrong energy input %g" % en)

        transm, vals = _transmission_calc.getAttenuation(en, transm, self.datafile)
        if not vals:
            raise RuntimeError(
                "No attenuators combination found for this energy: '%f`" % en
            )
        if -1 in vals:
            value = 0
        else:
            for i in vals:
                value += 1 << i
        self.__matt.mattstatus_set(value)

    def get(self):
        mystr = ""
        en = self.energy.read()
        if en <= 0:
            raise RuntimeError("Wrong energy input %g" % en)

        mystr = self.__matt._status_read()

        if not mystr:
            val = 100
        else:
            val = _transmission_calc.getAttenuationFactor(en, mystr, self.datafile)
        self.transmission_factor = val
        return val
