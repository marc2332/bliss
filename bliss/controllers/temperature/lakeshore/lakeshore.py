# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# from bliss.controllers.temp import Controller
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop
from bliss.common.utils import object_attribute_get, object_attribute_type_get
from bliss.common.utils import object_attribute_set, object_attribute_type_set


class Base(Controller):
    def __init__(self, handler, config, *args):
        self._lakeshore = handler
        Controller.__init__(self, config, *args)

    def initialize(self):
        """ Initializes the controller.
        """
        self._lakeshore.clear()

    def initialize_output(self, toutput):
        """Initialize the output device
        """
        self.__ramp_rate = None
        self.__set_point = None

    def initialize_loop(self, tloop):
        """Initialize the loop device
        """
        self.__kp = None
        self.__ki = None
        self.__kd = None

    def read_input(self, tinput):
        """Read the current temperature
           Returns:
              (float): current temperature
        """
        channel = tinput.config.get("channel")
        return self._lakeshore.read_temperature(channel)

    def read_output(self, toutput):
        """Read the setpoint temperature
           Returns:
              (float): setpoint temperature
        """
        channel = toutput.config.get("channel")
        return self._lakeshore.setpoint(channel)

    def set_ramprate(self, toutput, rate):
        """Set the ramp rate
           Args:
              rate (float): The ramp rate [K/min] - no action, cash value only.
        """
        channel = toutput.config.get("channel")
        self._lakeshore.ramp_rate(channel, rate)
        self.__ramp_rate = rate

    def read_ramprate(self, toutput):
        """Read the ramp rate
           Returns:
              (int): ramprate [K/min] - cashed cvalue only
        """
        channel = toutput.config.get("channel")
        self.__ramp_rate = self._lakeshore.ramp_rate(channel)
        return self.__ramp_rate

    # def start_ramp(self, toutput, sp, **kwargs):
    #     """Start ramping to setpoint
    #        Args:
    #           sp (float): The setpoint temperature [K]
    #        Kwargs:
    #           rate (int): The ramp rate [K/min]
    #        Returns:
    #           None
    #     """
    #     channel = toutput.config.get("channel")
    #     try:
    #         rate = float(kwargs.get("rate", self.__ramp_rate))
    #     except TypeError:
    #         raise RuntimeError("Cannot start ramping, ramp rate not set")
    #     self._lakeshore.ramp(channel, sp, rate)

    def on(self, tloop):
        """Start ramping to setpoint at the ramp rate [K/min]
           Args:
              tloop (int): loop number. 1 to 2.
           Returns:
              None
        """
        channel = toutput.config.get("channel")
        try:
            rate = float(kwargs.get("rate", self.__ramp_rate))
        except TypeError:
            raise RuntimeError("Cannot start ramping, ramp rate not set")
        self._lakeshore.ramp(channel, sp, rate)

    def set(self, toutput, sp, **kwargs):
        """Set the value of the output setpoint
           Args:
              sp (float): final temperature [K] or [deg]
           Returns:
              (float): current gas temperature setpoint
        """
        channel = toutput.config.get("channel")
        self._lakeshore.setpoint(channel, sp)
        self.__set_point = sp

    def get_setpoint(self, toutput):
        """Read the value of the output setpoint
           Returns:
              (float): current gas temperature setpoint
        """
        channel = toutput.config.get("channel")
        self.__set_point = self._lakeshore.setpoint(channel)
        return self.__set_point

    def set_kp(self, tloop, kp):
        """ Set the proportional gain
            Args:
               kp (float): value - 0.1 to 1000
            Returns:
               None
        """
        channel = tloop.config.get("channel")
        self._lakeshore.pid(channel, P=kp)
        self.__kp = kp

    def read_kp(self, tloop):
        """ Read the proportional gain
            Returns:
               kp (float): gain value - 0.1 to 1000
        """
        channel = tloop.config.get("channel")
        self.__kp, self.__ki, self.__kd = self._lakeshore.pid(channel)
        return self.__kp

    def set_ki(self, tloop, ki):
        """ Set the integral reset
            Args:
               ki (float): value - 0.1 to 1000 [value/s]
            Returns:
               None
        """
        channel = tloop.config.get("channel")
        self._lakeshore.pid(channel, I=ki)
        self.__ki = ki

    def read_ki(self, tloop):
        """ Read the integral reset
            Returns:
               ki (float): value - 0.1 to 1000
        """
        channel = tloop.config.get("channel")
        self.__kp, self.__ki, self.__kd = self._lakeshore.pid(channel)
        return self.__ki

    def set_kd(self, tloop, kd):
        """ Set the derivative rate
            Args:
               kd (float): value - 0 to 200 [%]
            Returns:
               None
        """
        channel = tloop.config.get("channel")
        self._lakeshore.pid(channel, D=kd)
        self.__kd = kd

    def read_kd(self, tloop):
        """ Read the derivative rate
            Returns:
               kd (float): value - 0 - 200
        """
        channel = tloop.config.get("channel")
        self.__kp, self.__ki, self.__kd = self._lakeshore.pid(channel)
        return self.__kd

    @object_attribute_type_get(type_info=("int"), type=Input)
    # get_model works only for input objects.
    def read_model(self, tinput):
        # self.log.info("get_model(= firmware identification string)")
        model = self._lakeshore.model()
        # self.log.debug("Firmware id string = %s" % model)
        return model

    @object_attribute_type_get(type_info=("int"), type=Output)
    def read_heater_range(self, toutput):
        channel = toutput.config.get("channel")
        htr_range = self._lakeshore.heater_range(channel)
        # print("--------- heater value = {0}".format(htr_range))
        return int(htr_range)

    @object_attribute_type_set(type_info=("int"), type=Output)
    def set_heater_range(self, toutput, value):
        channel = toutput.config.get("channel")
        print("--------- value = {0}".format(value))
        self._lakeshore.heater_range(channel, value)
