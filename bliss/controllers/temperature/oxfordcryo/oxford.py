# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.temp import Controller
from bliss.common.temperature import Output
from bliss.common.utils import object_method_type
from bliss import global_map


class Base(Controller):
    def __init__(self, handler, config, *args):
        Controller.__init__(self, config, *args)
        self._oxford = handler
        global_map.register(self, children_list=[handler])

    def read_output(self, toutput):
        """Read the current temperature
           Returns:
              (float): current temperature [K]
        """
        return self._oxford.read_temperature()

    def start_ramp(self, toutput, sp, **kwargs):
        """Start ramping to setpoint
           Args:
              sp (float): The setpoint temperature [K]
           Kwargs:
              rate (int): The ramp rate [K/hour]
           Returns:
              None
        """
        rate = self._oxford.read_ramprate()
        self._oxford.ramp(rate, sp)

    def set_ramprate(self, toutput, rate):
        """Set the ramp rate
           Args:
              rate (int): The ramp rate [K/hour]
        """
        target_temperature = self._oxford.read_target_temperature()
        self._oxford.ramp(rate, target_temperature)

    def read_ramprate(self, toutput):
        """Read the ramp rate
           Returns:
              (int): Previously set ramp rate (cashed value only) [K/hour]
        """
        return self._oxford.read_ramprate()

    def set(self, toutput, sp, **kwargs):
        """Make gas temperature decrease to a set value as quickly as possible
           Args:
              sp (float): final temperature [K]
           Returns:
              (float): current gas temperature setpoint
        """
        return self._oxford.cool(sp)

    def get_setpoint(self, toutput):
        """Read the as quick as possible setpoint
           Returns:
              (float): current gas temperature setpoint
        """
        self.__set_point = self._oxford.cool()
        return self.__set_point

    @object_method_type(types_info=("bool", "None"), type=Output)
    def turbo(self, toutput, flow):
        """Switch on/off the turbo gas flow
           Args:
              flow (bool): True when turbo is on (gas flow 10 l/min)
           Returns:
              None
        """
        self._oxford.turbo(flow)

    @object_method_type(types_info=("bool", "None"), type=Output)
    def pause(self, toutput, off=None):
        if off:
            self._oxford.resume()
        else:
            self._oxford.pause()

    @object_method_type(types_info=("None", "None"), type=Output)
    def hold(self, toutput):
        self._oxford.hold()

    @object_method_type(types_info=("None", "None"), type=Output)
    def restart(self, toutput):
        self._oxford.restart()

    @object_method_type(types_info=("int", "int"), type=Output)
    def plat(self, toutput, duration=None):
        """Maintain temperature fixed for a certain time.
           Args:
              duration (int): time [minutes]
           Returns:
              (int): remaining time [minutes]
        """
        return self._oxford.plat(duration)

    @object_method_type(types_info=("int", "None"), type=Output)
    def end(self, toutput, rate):
        """System shutdown with Ramp Rate to go back to temperature of 300K
           Args:
              rate (int): ramp rate [K/hour]
        """
        self._oxford.end(rate)
