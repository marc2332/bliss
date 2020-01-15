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
    def PumpMode(self):
        return self.controller.PumpMode

    @autocomplete_property
    def pump_auto(self):
        return self.controller.get_pump_auto()

    @pump_auto.setter
    def pump_auto(self, value):
        return self.controller.set_pump_auto(value)

    @autocomplete_property
    def pump_speed(self):
        return self.controller.get_pump_speed()

    @pump_speed.setter
    def pump_speed(self, value):
        return self.controller.set_pump_speed(value)

    def heat(self):
        self.controller.heat()

    def cool(self):
        self.controller.cool()


class LinkamLoop(Loop):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller.state())

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @property
    @lazy_init
    def regulation_info(self):
        """ Read:
                - the stored rate
                - the stored setpoint
                - the current stage status (stopped, heating, etc.)
        """
        self.controller.clear(self)
        regulation_dict = {}
        regulation_dict["rate"] = self.controller.get_ramprate(self)
        regulation_dict["sp"] = self.controller.get_setpoint(self)
        regulation_dict["status"] = self.controller.is_ramping(self)
        return regulation_dict

    def hold(self):
        self.controller.set_hold_on(self)
