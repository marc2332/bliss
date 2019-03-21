# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# from bliss.controllers.temp import Controller
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop

# Next 3 are no more necessary since we do not use 'standard'
# way of doing custom commands and attributes but rather define/add
# them in initialize methods for each type of object (input, output, loop)

# from bliss.common.utils import object_attribute_get, object_attribute_type_get
# from bliss.common.utils import object_attribute_set, object_attribute_type_set
# from bliss.common.utils import object_method


class Base(Controller):
    def __init__(self, handler, config, *args):
        self._lakeshore = handler
        Controller.__init__(self, config, *args)

    def initialize(self):
        """ Initializes the controller.
        """
        self._lakeshore.clear()

    def initialize_input(self, tinput):
        """Initialize the input device
        """
        if hasattr(self._lakeshore, "_initialize_input"):
            self._lakeshore._initialize_input(tinput)

    def initialize_output(self, toutput):
        """Initialize the output device
        """
        self.__ramp_rate = None
        self.__set_point = None
        if hasattr(self._lakeshore, "_initialize_output"):
            self._lakeshore._initialize_output(toutput)

    def initialize_loop(self, tloop):
        """Initialize the loop device
        """
        self.__kp = None
        self.__ki = None
        self.__kd = None
        if hasattr(self._lakeshore, "_initialize_loop"):
            self._lakeshore._initialize_loop(tloop)

    # Input-object related methods
    # ----------------------------
    def read_input(self, tinput):
        """Read the current temperature
           Returns:
              (float): current temperature in Kelvin or Celsius 
                       or sensor-unit reading (Ohm or Volt)
                       depending on read_type.
        """
        channel = tinput.config.get("channel")
        read_type = tinput.config.get("type", "temperature_K")
        if read_type == "temperature_K":
            return self._lakeshore.read_temperature(channel, "kelvin")
        elif read_type == "temperature_C":
            return self._lakeshore.read_temperature(channel, "celsius")
        elif read_type == "sensorunit":
            # sensor unit can be Ohm or Volt depending on sensor type
            return self._lakeshore.read_insensorunits(channel)

    # the method state_input(self, tinput) is not implemented
    # (is inherited from temp.py)

    # Output-object related methods
    # -----------------------------

    # the method state_output(self, toutput) is not implemented
    # (is inherited from temp.py)

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
              (int): ramprate [K/min]
        """
        channel = toutput.config.get("channel")
        self.__ramp_rate = self._lakeshore.ramp_rate(channel)
        return self.__ramp_rate

    # the methods:
    # set_dwell(self, toutput, dwell)
    # read_dwell(self, toutput)
    # set_step(self, toutput, step)
    # read_step(self, toutput)
    # are not implemented
    # (are inherited from temp.py)

    def start_ramp(self, toutput, sp, **kwargs):
        """Start ramping to setpoint
           Args:
              sp (float): The setpoint temperature [K]
           Kwargs:
              rate (int): The ramp rate [K/min]
           Returns:
              None
        """
        channel = toutput.config.get("channel")
        rate = kwargs.get("rate")
        if rate == None:
            if self.__ramp_rate != None:
                rate = self.__ramp_rate
            else:
                raise RuntimeError("Cannot start ramping, ramp rate not set")
        else:
            self.__ramp_rate = rate
        self.__set_point = sp
        self._lakeshore.ramp(channel, sp, rate)

    def setpoint_stop(self, toutput):
        """Stop the ramping going to setpoint
        """
        channel = toutput.config.get("channel")
        # if ramp is active, disable it
        ramp_stat = self._lakeshore._rampstatus(channel)
        if ramp_stat == 1:
            rate = self.__ramp_rate
            print("rate = {0}".format(rate))
            # setting ramp rate causes ramping off
            self._lakeshore.ramp_rate(channel, rate)

    def setpoint_abort(self, toutput):
        """Emergency stop the going to setpoint.
           Switch off the heater.
        """
        # set heater range to 0, which means heater power OFF
        self._lakeshore.heater_range(0)

    # Loop-object related methods
    # ---------------------------
    def on(self, tloop):
        """Start the regulation on loop
           Args:
              tloop (int): loop number. 1 to 2.
           Returns:
              None
        """
        channel = tloop.config.get("channel")

        self._lakeshore._cset(channel, onoff="on")
        (input, units, onoff) = self._lakeshore._cset(channel)

    def off(self, tloop):
        """Stop the regulation on loop
           Args:
              tloop (int): loop number. 1 to 2.
           Returns:
              None
        """
        channel = tloop.config.get("channel")

        self._lakeshore._cset(channel, onoff="off")
        (input, units, onoff) = self._lakeshore._cset(channel)

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

    # Raw communication methods, callable from any
    # type of object (Input/Output/Loop)
    # --------------------------------------------
    def Wraw(self, string):

        """
        A string to write to the controller

        Args:
           string:  the string to write
        """
        self._lakeshore.wraw(string)

    def Rraw(self):
        """
        Reading the controller

        returns:
           response from the controller
        """
        ans = self._lakeshore.rraw()
        return ans

    def WRraw(self, string):
        """
        Write then Reading the controller

        Args:
           string:  the string to write
        returns:
           response from the controller
        """
        ans = self._lakeshore.wrraw(string)
        return ans
