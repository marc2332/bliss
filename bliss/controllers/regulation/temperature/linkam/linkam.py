# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
End user API for the Linkam regulation objects
      input: $linkam1_in
      output: $linkam1_out
"""

from bliss.shell.standard import ShellStr
from bliss.common.regulation import Input, Output, Loop, lazy_init
from bliss.common.utils import autocomplete_property


class LinkamInput(Input):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.state())

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @lazy_init
    def dsc(self):
        """ 
        Ask the temperature and the DSC data value
        which were sampled at the same time
        and is not the same that the read temperature
        which could be delayed by windows data collection.
        Args:
            None
        
        Returns:
            The temperature and the DSC value in int.
        """
        return self.controller.dsc()


class LinkamOutput(Output):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.state())

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @autocomplete_property
    def pump_mode_enum(self):
        return self.controller.PumpMode

    @property
    @lazy_init
    def valid_pump_modes(self):
        lines = ["\n"]
        for pme in self.controller.PumpMode:
            lines.append(f"{pme.name} = {pme.value}")
        return ShellStr("\n".join(lines))

    @property
    @lazy_init
    def pump_auto(self):
        return self.controller.get_pump_auto()

    @pump_auto.setter
    @lazy_init
    def pump_auto(self, value):
        return self.controller.set_pump_auto(value)

    @property
    @lazy_init
    def pump_speed(self):
        return self.controller.get_pump_speed()

    @pump_speed.setter
    @lazy_init
    def pump_speed(self, value):
        return self.controller.set_pump_speed(value)

    @lazy_init
    def heat(self):
        self.controller.heat()

    @lazy_init
    def cool(self):
        self.controller.cool()


class LinkamLoop(Loop):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.state())

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @lazy_init
    def hold(self):
        self.controller.set_hold_on(self)
