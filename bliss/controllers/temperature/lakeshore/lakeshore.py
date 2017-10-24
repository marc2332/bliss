# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output


class Base(Controller):
    def __init__(self, handler, config, *args):
        Controller.__init__(self, config, *args)
        self._lakeshore = handler

    def initialize(self):
        """ Initializes the controller.
        """
        self._lakeshore.clear()

    def read_input(self, tinput):
        """Read the current temperature
           Returns:
              (float): current temperature
        """
        return self._lakeshore.read_temperature()

    def initialize_output(self, toutput):
        """Initialize the output device
        """
        self.__ramp_rate = None
        self.__set_point = None

    def start_ramp(self, toutput, sp, **kwargs):
        """Start ramping to setpoint
           Args:
              sp (float): The setpoint temperature [K]
           Kwargs:
              rate (int): The ramp rate [K/min]
           Returns:
              None
        """
        try:
            rate = float(kwargs.get("rate", self.__ramp_rate))
        except TypeError:
            raise RuntimeError("Cannot start ramping, ramp rate not set")
        self._lakeshore.ramp(sp, rate)

    def set_ramprate(self, toutput, rate):
        """Set the ramp rate
           Args:
              rate (float): The ramp rate [K/min] - no action, cash value only.
        """
        # self._lakeshore.set_ramp_rate(rate, 0)
        self.__ramp_rate = rate

    def read_ramprate(self, toutput):
        """Read the ramp rate
           Returns:
              (int): ramprate [K/min] - cashed cvalue only
        """
        # self.__ramp_rate = self._lakeshore.read_ramp_rate()
        return self.__ramp_rate

    def set(self, toutput, sp, **kwargs):
        """Set the value of the output setpoint
           Args:
              sp (float): final temperature [K] or [deg]
           Returns:
              (float): current gas temperature setpoint
        """
        return self._lakeshore.setpoint(sp)

    def get_setpoint(self, toutput):
        """Read the value of the output setpoint
           Returns:
              (float): current gas temperature setpoint
        """
        self.__set_point = self._lakeshore.setpoint()
        return self.__set_point
