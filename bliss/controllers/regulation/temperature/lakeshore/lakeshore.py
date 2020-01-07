# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.regulator import Controller
from bliss.common.regulation import Input, Output, Loop, lazy_init
from bliss.common.logtools import log_info
from bliss.common.utils import autocomplete_property
from bliss import global_map
import os
import re
import sys
import enum


class Curve:
    def __init__(self, input_object):
        self.controller = input_object.controller
        self.channel = input_object.config.get("channel")

    @property
    def used(self):
        """ Get the input curve used
            Args:
              channel (str): input channel. Valied entries: A or B
            Prints:
              curve number (int): 0=none, 1->20 standard, 21->41 user defined curves
              curve name (str): limited to 15 characters
              curve SN (str): limited to 10 characters (Standard,...)
              curve format (int): 1=mV/K, 2=V/K, 3=Ohms/K, 4=logOhms/K
              curve temperature limit (float): in Kelvin
              curve temperature coefficient (int): 1=negative, 2=positive
        """
        return self.controller._used_curve(self.channel)

    def select(self, crvn):
        """ Set the curve to be used on a given input.
            Warning: the specified has to match with the type input.
            If not, the set curve number is 0 :(
            Hint: Set
              crvn (int): curve number: 0=none, 1->20 standard,
                                        21->41 user defined
        Returns:
            None
        """
        return self.controller._select(crvn, self.channel)

    def list_all(self):
        return self.controller._list_all()

    def load(self, crvn, crvfile):
        return self.controller._write(crvn, crvfile)

    def delete(self, crvn):
        return self.controller._delete(crvn)


class LakeshoreInput(Input):
    @autocomplete_property
    @lazy_init
    def curve(self):
        return Curve(self)

    @lazy_init
    def __info__(self):
        return "\n".join(self.controller._show(self.name))

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @lazy_init
    def filter(self, onoff=None, points=None, window=None):
        """ Configure input filter parameters
        Args:
            onoff (int): 1 = enable, 0 = disable
            points (int): specifies how many points the filtering 
                          function uses. Valid range: 2 to 64
            window (int): specifies what percent of full scale 
                          reading limits the filtering function. 
                          Reading changes greater than this percentage
                          reset the filter. Valid range: 1 to 10%.
        
        Returns:
            None
        """
        return self.controller._lakeshore._filter(
            self.config.get("channel"), onoff=onoff, points=points, window=window
        )

    @lazy_init
    def sensor_type(self, **kwargs):
        """ Configure input type parameters
            Hint: check the _sensor_type help in the Class Controller
                  according to the manual
        Returns:
            the args according to the model
        """
        """Set input type unit according to the controller"""
        channel = self.config.get("channel")
        return self.controller._lakeshore._sensor_type(channel, **kwargs)

    @lazy_init
    def alarm_status(self):
        """ Shows high and low alarm state for given input
            Args:
              None
            Returns:
              high and low alarm state (str, str): "On/Off"
        """
        log_info(self, "alarm_status")
        channel = self.config.get("channel")
        return self.controller._lakeshore._alarm_status(channel)

    @lazy_init
    def alarm_reset(self):
        """ Clears both the high and low status of all alarms
            Args:
              None (though this command does not need the input channel,
                    we put it here, since alarms are related to the state
                    on input like for ex. measured temperature above 
                    alarm high-limit etc.)
            Returns:
              None
        """
        log_info(self, "alarm_reset")
        return self.controller._lakeshore._alarm_reset()


class LakeshoreOutput(Output):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller._show(self.name))

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @property
    @lazy_init
    def value_percent(self):
        channel = self.config.get("channel", int)
        return self.controller._read_value_percent(channel)

    @autocomplete_property
    def HeaterRange(self):
        return self.controller.HeaterRange

    @property
    @lazy_init
    def range(self):
        channel = self.config.get("channel", int)
        return self.controller._read_heater_range(channel)

    @range.setter
    @lazy_init
    def range(self, value):
        channel = self.config.get("channel", int)
        return self.controller._set_heater_range(channel, value)


class LakeshoreLoop(Loop):
    @lazy_init
    def __info__(self):
        return "\n".join(self.controller._show(self.name))

    def __str__(self):
        # this is for the mapping: it needs a representation of instance
        return super().__repr__()

    @autocomplete_property
    def Mode(self):
        return self.controller.Mode

    @property
    @lazy_init
    def mode(self):
        channel = self.config.get("channel", int)
        return self.controller._read_loop_mode(channel)

    @mode.setter
    @lazy_init
    def mode(self, mode):
        channel = self.config.get("channel", int)
        return self.controller._set_loop_mode(channel, mode)

    @property
    @lazy_init
    def params(self):
        channel = self.config.get("channel", int)
        return self.controller._lakeshore.read_loop_params(channel)

    ## UNUSED on purpose. The channel input is set with YML file.
    # @params.setter
    # def params(self, input, unit):
    #    channel = self.config.get("channel", int)
    #    return self.controller._lakeshore.set_loop_params(channel, input, unit)
    # The parameters are set with the YML file.

    @autocomplete_property
    def Unit(self):
        return self.controller.Unit

    @property
    @lazy_init
    def unit(self):
        if self.controller._lakeshore._model() in range(335, 337):
            channel = self.input.config.get("channel")
        else:
            channel = self.config.get("channel")
        return self.controller._read_loop_unit(channel)

    @unit.setter
    @lazy_init
    def unit(self, unit):
        if self.controller._lakeshore._model() in range(335, 337):
            channel = self.input.config.get("channel")
        else:
            channel = self.config.get("channel")
        return self.controller._set_loop_unit(channel, unit)

    @enum.unique
    class INPUT(enum.IntEnum):
        none = 0
        A = 1
        B = 2
        C = 3
        D = 4

    @property
    @lazy_init
    def ramp_info(self):
        channel = self.output.config.get("channel", int)
        ramp_dict = self.controller._lakeshore.ramp_rate(channel)
        sp = self.controller._lakeshore.setpoint(channel)  # self.set()
        ramp_dict["sp"] = sp
        # Read ramp status (only if ramp is enabled)
        ramp_dict["ramp_state"] = "NOT RAMPING"
        if ramp_dict["state"] == "ON" and self.controller._lakeshore.ramp_status(
            channel
        ):
            ramp_dict["ramp_state"] = "RAMPING"

        return ramp_dict


class LakeshoreBase(Controller):
    """
    Regulation controller base class

    The 'Controller' class should be inherited by controller classes that are linked to an hardware 
    which has internal PID regulation functionnalities and optionally ramping functionnalities (on setpoint or output value) .
    
    If controller hardware does not have ramping capabilities, the Loop objects associated to the controller will automatically use a SoftRamp.

    """

    def __init__(self, handler, config):

        self._lakeshore = handler

        Controller.__init__(self, config)
        global_map.register(handler._comm, parents_list=[self, "comms"])

    # ------ init methods ------------------------

    def initialize_controller(self):
        """ 
        Initializes the controller.
        """
        self._lakeshore.clear()

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        self._lakeshore._initialize_input(tinput)

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        # self.__ramp_rate = None
        # self.__set_point = None
        self._lakeshore._initialize_output(toutput)

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        # self.__kp = None
        # self.__ki = None
        # self.__kd = None
        self._lakeshore._initialize_loop(tloop)

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """Read the current temperature
           Returns:
              (float): current temperature in Kelvin or Celsius 
                       or sensor-unit reading (Ohm or Volt)
                       depending on read_type.
        """
        log_info(self, "Controller:read_input: %s" % (tinput))
        channel = tinput.config.get("channel")
        read_unit = tinput.config.get("unit", "Kelvin")
        if read_unit == "Kelvin":
            try:
                return self._lakeshore.read_temperature(channel, "Kelvin")
            except ValueError:
                return float("NAN")
        elif read_unit == "Celsius":
            try:
                return self._lakeshore.read_temperature(channel, "Celsius")
            except ValueError:
                return float("NAN")
        elif read_unit == "Sensor_unit":
            try:
                # sensor unit can be Ohm or Volt depending on sensor type
                return self._lakeshore.read_temperature(channel, "Sensor_unit")
            except ValueError:
                return float("NAN")

    def read_output(self, toutput):
        # cannot read the output value so return the setopoint value instead
        """Read the setpoint temperature
           Returns:
              (float): setpoint temperature
        """
        log_info(self, "Controller:read_output: %s" % (toutput))
        # channel = toutput.config.get("channel")
        # self.__set_point = self._lakeshore.setpoint(channel)
        # return self.__set_point
        # raise NotImplementedError
        # return self._lakeshore.setpoint(channel)
        return float(toutput.value_percent)

    def state_output(self, toutput):
        """
        Return a string representing state of the Output.

        Args:
           toutput:  Output class type object

        Returns:
           object state string. 
        """
        log_info(self, "Controller:state_output: %s" % (toutput))
        channel = toutput.config.get("channel")
        return self._read_state_output(channel)

    # ------ raw methods ------------------------

    def Wraw(self, string):
        """
        A string to write to the controller

        Args:
           string:  the string to write
        """
        log_info(self, "Controller:Wraw:")
        self._lakeshore.wraw(string)

    def Rraw(self):
        """
        Reading the controller

        returns:
           response from the controller
        """
        log_info(self, "Controller:Rraw:")
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
        log_info(self, "Controller:WRraw:")
        ans = self._lakeshore.wrraw(string)
        return ans

    # ------ PID methods ------------------------

    def set_kp(self, tloop, kp):
        """ Set the proportional gain
            Args:
               kp (float): value - 0.1 to 1000
            Returns:
               None
        """
        log_info(self, "Controller:set_kp: %s %s" % (tloop, kp))

        channel = tloop.config.get("channel")
        self._lakeshore.pid(channel, P=kp)
        # self.__kp = kp

    def get_kp(self, tloop):
        """ Read the proportional gain
            Returns:
               kp (float): gain value - 0.1 to 1000
        """
        log_info(self, "Controller:get_kp: %s" % (tloop))

        channel = tloop.config.get("channel")
        # self.__kp, self.__ki, self.__kd = self._lakeshore.pid(channel)
        # return self.__kp
        kp, ki, kd = self._lakeshore.pid(channel)
        return kp

    def set_ki(self, tloop, ki):
        """ Set the integral reset
            Args:
               ki (float): value - 0.1 to 1000 [value/s]
            Returns:
               None
        """
        log_info(self, "Controller:set_ki: %s %s" % (tloop, ki))
        channel = tloop.config.get("channel")
        self._lakeshore.pid(channel, I=ki)
        # self.__ki = ki

    def get_ki(self, tloop):
        """ Read the integral reset
            Returns:
               ki (float): value - 0.1 to 1000
        """
        log_info(self, "Controller:get_ki: %s" % (tloop))
        channel = tloop.config.get("channel")
        # self.__kp, self.__ki, self.__kd = self._lakeshore.pid(channel)
        # return self.__ki
        kp, ki, kd = self._lakeshore.pid(channel)
        return ki

    def set_kd(self, tloop, kd):
        """ Set the derivative rate
            Args:
               kd (float): value - 0 to 200 [%]
            Returns:
               None
        """
        log_info(self, "Controller:set_kd: %s %s" % (tloop, kd))
        channel = tloop.config.get("channel")
        self._lakeshore.pid(channel, D=kd)
        # self.__kd = kd

    def get_kd(self, tloop):
        """ Read the derivative rate
            Returns:
               kd (float): value - 0 - 200
        """
        log_info(self, "Controller:get_kd: %s" % (tloop))
        channel = tloop.config.get("channel")
        # self.__kp, self.__ki, self.__kd = self._lakeshore.pid(channel)
        # return self.__kd
        kp, ki, kd = self._lakeshore.pid(channel)
        return kd

    def start_regulation(self, tloop):
        """
        Starts the regulation process.
        It must NOT start the ramp, use 'start_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:start_regulation: %s" % (tloop))

        self._set_loop_on(tloop)

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.
        It must NOT stop the ramp, use 'stop_ramp' to do so.
        Raises NotImplementedError if not defined by inheriting class

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "Controller:stop_regulation: %s" % (tloop))

        self._set_loop_off(tloop)

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """Set the value of the output setpoint
           Args:
              sp (float): final temperature [K] or [deg]
           Returns:
              (float): current gas temperature setpoint
        """
        log_info(self, "Controller:set_setpoint: %s %s" % (tloop, sp))
        channel = tloop.output.config.get("channel")
        self._lakeshore.setpoint(channel, sp)
        self.last_set_point = sp

    def get_setpoint(self, tloop):
        """Read the value of the output setpoint
           Returns:
              (float): current gas temperature setpoint
        """
        log_info(self, "Controller:get_setpoint: %s" % (tloop))
        channel = tloop.output.config.get("channel")
        # self.__set_point = self._lakeshore.setpoint(channel)
        # return self.__set_point
        return self._lakeshore.setpoint(channel)

    # ------ setpoint ramping methods ------------------------

    def start_ramp(self, tloop, sp, **kwargs):  # TO BE TESTED
        """Start ramping to setpoint
           Args:
              sp (float): The setpoint temperature [K]
           Kwargs:
              rate (int): The ramp rate [K/min]
           Returns:
              None
        """
        log_info(self, "Controller:start_ramp: %s %s" % (tloop, sp))
        channel = tloop.output.config.get("channel")
        rate = kwargs.get("rate")
        # if rate is None:
        #    rate = self._lakeshore.ramp_rate(channel)["rate"]
        # self.__ramp_rate = rate
        # self.__set_point = sp

        if rate is None:
            rate = self.get_ramprate(tloop)
        else:
            self.set_ramprate(tloop, rate)

        self._lakeshore.ramp(channel, sp, rate)

    def stop_ramp(self, tloop):
        """Stop the ramping going to setpoint
        """
        log_info(self, "Controller:stop_ramp: %s" % (tloop))
        # if ramp is active, disable it
        if self.is_ramping(tloop):
            # setting ramp rate causes ramping off
            rate = self.get_ramprate(tloop)
            self.set_ramprate(tloop, rate)

    def is_ramping(self, tloop):
        """
        Get the ramping status.
        Raises NotImplementedError if not defined by inheriting class

        Args:
           tloop:  Loop class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "Controller:is_ramping: %s" % (tloop))

        channel = tloop.output.config.get("channel")
        ramp_stat = self._lakeshore.ramp_status(channel)
        if ramp_stat == 1:
            return True
        else:
            return False

    def set_ramprate(self, tloop, rate):
        """Set the ramp rate
           Args:
              rate (float): The ramp rate [K/min] - no action, cash value only.
        """
        log_info(self, "Controller:set_ramprate: %s %s" % (tloop, rate))
        channel = tloop.output.config.get("channel")
        self._lakeshore.ramp_rate(channel, rate)
        # self.__ramp_rate = rate

    def get_ramprate(self, tloop):
        """Read the ramp rate
           Returns:
              (int): ramprate [K/min]
        """
        log_info(self, "Controller:get_ramprate: %s" % (tloop))
        channel = tloop.output.config.get("channel")
        # self.__ramp_rate = self._lakeshore.ramp_rate(channel)["rate"]
        # return self.__ramp_rate
        return self._lakeshore.ramp_rate(channel)["rate"]

    # ------ others ------------------------------

    def _f(self):
        pass

    def set_in_safe_mode(self, toutput):
        """
        Set the output in a safe mode (like stop heating)
        Raises NotImplementedError if not defined by inheriting class

        Args:
           toutput:  Output class type object 
        """
        log_info(self, "Controller:set_in_safe_mode: %s" % (toutput))

        toutput.range = 0

    # ----- Controller specific -----------------

    @autocomplete_property
    def HeaterState(self):
        return self.controller.HeaterState

    @property
    def model(self):
        """ Get the model number
        Returns:
        model (int): model number
        """
        log_info(self, "Controller:model")
        return self._lakeshore._model()

    def _show(self, name=None):
        """ Display all main parameters and values for the temperature controller
            Prints:
              device ID, PID, heater range, loop status, sensors configuration, inputs temperature etc.
        """
        repr_list = []
        log_info(self, "Controller:_show")
        # Get full identification string
        full_id = self._lakeshore.send_cmd("*IDN?")
        repr_list.append("Lakeshore identification %s" % (full_id))

        # inputs
        sensor = self.inputs.get(name)
        if sensor is not None:
            repr_list.append(f"\nInput {name} :\n{'='*(len(name)+9)}")
            curve_dict = sensor.curve.used
            if curve_dict["curve_number"]:
                repr_list.append(
                    f"Uses calibration curve number {curve_dict['curve_number']}"
                )
                repr_list.append(
                    "Name: %(curve_name)s\tSN: %(curve_sn)s\tFormat: %(curve_format)s"
                    % curve_dict
                )
                repr_list.append(
                    "Temperature limit: %(curve_temperature_limit)s\tTemp. coefficient: %(curve_temperature_coefficient)s"
                    % curve_dict
                )
            repr_list.append("Sensor type: %s" % sensor.sensor_type())
            repr_list.append(
                "Temperature: %.3f %s" % (sensor.read(), sensor.config.get("unit"))
            )
        # outputs
        output = self.outputs.get(name)
        if output is not None:
            repr_list.append(f"\nOutput {name} :\n{'='*(len(name)+9)}")
            repr_list.append("Heater range is %s" % output.range.name)
            # Get heater status
            repr_list.append("Heater status is %s" % self.state_output(self))
            # Get heater power
            htr_power = float(output.value_percent)
            repr_list.append("Heater power = %.1f %%" % htr_power)
            # ramp_dict = output.ramp_info
            # repr_list.append(
            #    "Ramp enable is %(state)s with setpoint: %(sp)s and ramp-rate: %(rate).3f K/min.\nRamp state is %(ramp_state)s"
            #    % ramp_dict
            # )

        # loops
        loop = self.loops.get(name)
        if loop is not None:
            repr_list.append(f"\nLoop {name} :\n{'='*(len(name)+7)}")
            params_dict = loop.params
            if re.search(r"[1-4]", params_dict["input"]):
                params_dict["input"] = loop.INPUT(int(params_dict["input"]))
            repr_list.append("Controlled by sensor %(input)s in %(unit)s" % params_dict)
            repr_list.append("Temp. control is set to %s" % loop.mode)
            repr_list.append("PID parameters")
            repr_list.append(
                "P: %.1f\tI: %.1f\tD: %.1f"
                % (float(loop.kp), float(loop.ki), float(loop.kd))
            )

            ramp_dict = loop.ramp_info
            repr_list.append(
                "Ramp enable is %(state)s with setpoint: %(sp)s and ramp-rate: %(rate).3f K/min.\nRamp state is %(ramp_state)s"
                % ramp_dict
            )

        return repr_list

    def _used_curve(self, channel):
        log_info(self, "Controller:_used_curve")
        curve_number = self._lakeshore.send_cmd("INCRV?", channel=channel)
        command = "CRVHDR? %s" % curve_number
        curve_header = self._lakeshore.send_cmd(command, channel=channel)
        header = curve_header.split(",")
        curve_name = header[0]
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT[int(header[2])]
        curve_temperature_limit = header[3]
        curve_temperature_coefficient = self.CURVETEMPCOEF[int(header[4])]
        return {
            "curve_number": int(curve_number),
            "curve_name": curve_name,
            "curve_sn": curve_sn,
            "curve_format": curve_format,
            "curve_temperature_limit": curve_temperature_limit,
            "curve_temperature_coefficient": curve_temperature_coefficient,
        }

    def _select(self, crvn, channel):
        log_info(self, f"Controller:_select_curve: {crvn}")
        if crvn not in range(1, self.NCURVES + 1):
            raise ValueError(
                f"Curve number {crvn} is invalid. Should be [1,{self.NCURVES-1}]"
            )
        else:
            self._lakeshore.send_cmd("INCRV", crvn, channel=channel)

    def _list_all(self):
        """ List all the curves
            Returns:
              a row for all the curves from 1 to the number of available ones
        """
        log_info(self, "Controller:_list_all")
        print(" #            Name       SN         Format     Limit(K) Temp. coef.")
        for i in range(1, self.NCURVES + 1):
            command = "CRVHDR? %s" % i
            curve_header = self._lakeshore.send_cmd(command)
            header = curve_header.split(",")
            curve_name = header[0].strip()
            curve_sn = header[1]
            curve_format = self.CURVEFORMAT[int(header[2])]
            curve_temperature_limit = header[3]
            curve_temperature_coefficient = self.CURVETEMPCOEF[int(header[4])]
            print(
                "%2d %15s %10s %12s %12s %s"
                % (
                    i,
                    curve_name,
                    curve_sn,
                    curve_format,
                    curve_temperature_limit,
                    curve_temperature_coefficient,
                )
            )

    def _write(self, crvn, crvfile):
        log_info(self, "Controller:_curve_write")
        user_min_curve, user_max_curve = self.NUSERCURVES

        if crvn not in range(user_min_curve, user_max_curve + 1):
            raise ValueError(
                "User curve number %d is not in [%d,%d]"
                % (crvn, user_min_curve, user_max_curve)
            )

        if os.path.isfile(crvfile) == False:
            raise FileNotFoundError("Curve file %s not found" % crvfile)

        print("Readings from actual curve %d in LakeShore 331 :" % crvn)
        command = "CRVHDR? %d" % crvn
        loaded_curve = self._lakeshore.send_cmd(command)
        header = loaded_curve.split(",")
        curve_name = header[0].strip()
        curve_sn = header[1]
        curve_format = self.CURVEFORMAT[int(header[2])]
        curve_temp_limit = header[3]
        curve_temp_coeff = self.CURVETEMPCOEF[int(header[4])]
        print(
            "\t%15s %10s %12s %12s %s"
            % (curve_name, curve_sn, curve_format, curve_temp_limit, curve_temp_coeff)
        )

        with open(crvfile) as f:
            for line in f:
                # print(line)
                if line.count(":") == 1:
                    lline = line.split(":")
                    print(lline[0] + lline[1])
                    if lline[0] == "Sensor Model":
                        curve_name = lline[1].strip()
                    if lline[0] == "Serial Number":
                        curve_sn = lline[1].strip()
                    if lline[0] == "Data Format":
                        curve_format_long = lline[1]
                        curve_format = curve_format_long.split(None, 1)[0]

                    if lline[0] == "SetPoint Limit":
                        curve_temp_limit_long = lline[1]
                        curve_temp_limit = curve_temp_limit_long.split(None, 1)[0]

                    if lline[0] == "Temperature coefficient":
                        curve_temp_coeff_long = lline[1]
                        curve_temp_coeff = curve_temp_coeff_long.split(None, 1)[0]

                    if lline[0] == "Number of Breakpoints":
                        curve_nb_breakpts = lline[1].strip()

            # checking header values
            if curve_name == "":
                raise ValueError("No sensor model")
            if curve_sn == "":
                raise ValueError("No serial number")
            if curve_format_long == "":
                raise ValueError("No data format")
            elif int(curve_format) not in range(1, 5):
                raise ValueError("Curve data format %s not in [1,4]" % curve_format)
            if curve_temp_limit_long == "":
                raise ValueError("No setpoint limit")
            if curve_temp_coeff_long == "":
                raise ValueError("No temperature coefficient")
            elif int(curve_temp_coeff) not in range(1, 3):
                raise ValueError(
                    "Curve temperature coefficient %s not in [1,2]" % curve_temp_coeff
                )
            if curve_nb_breakpts == "":
                raise ValueError("No number of breakpoints")
            elif int(curve_nb_breakpts) not in range(1, 201):
                raise ValueError(
                    "Number of breakpoints %s not in [1,200]" % curve_nb_breakpts
                )

        # writing the curve header into the Lakeshore
        command = "CRVHDR %d,%s,%s,%d,%f,%d" % (
            crvn,
            curve_name,
            curve_sn,
            int(curve_format),
            float(curve_temp_limit),
            int(curve_temp_coeff),
        )
        print(command)
        self._lakeshore.send_cmd(command)
        calibrationStart = 0
        breakpts = 0
        with open(crvfile) as f:
            for line in f:
                if calibrationStart == 0:
                    exp = re.compile(r"^\s*1\s+")
                    if exp.match(line):
                        calibrationStart = 1
                if calibrationStart:
                    l = line.strip(" ")
                    ll = l.rsplit()
                    if len(ll) == 3:
                        command = "CRVPT %d,%d,%6g,%6g" % (
                            crvn,
                            int(ll[0]),
                            float(ll[1]),
                            float(ll[2]),
                        )
                        sys.stdout.write(
                            "Writing curve %d with data point %s\r" % (crvn, command)
                        )
                        self._lakeshore.send_cmd(command)
                        breakpts += 1
        if breakpts == int(curve_nb_breakpts):
            print(
                "\nCurve %d has been written into the LakeShore model 331 temperature controller."
                % crvn
            )
            # Reading back for checking the header
            command = "CRVHDR? %d" % crvn
            curve_header = self._lakeshore.send_cmd(command)
            print("The header read back for the %d is:" % crvn)
            print(curve_header)
            if self.model == 340:
                print("Updating the curve flash with the current user curves.")
                print("May take several seconds.")
                self._lakeshore.send_cmd("CRVSAV")
        else:
            print(
                "Error. The number of breakpoints written (%d) does not match with %d."
                % (breakpts, int(curve_nb_breakpts))
            )

    def _delete(self, crvn):
        log_info(self, f"Controller:_delete: {crvn}")
        user_min_curve, user_max_curve = self.NUSERCURVES

        if crvn is None:
            crvn = input(
                "Number of curve to be deleted [%d,%d]?"
                % (user_min_curve, user_max_curve)
            )
        else:
            log_info(self, "Curve number passed as arg = %d" % crvn)

        if crvn not in range(user_min_curve, user_max_curve + 1):
            raise ValueError(
                "User curve number %d is not in [%d,%d]"
                % (crvn, user_min_curve, user_max_curve)
            )

        # Delete the curve
        command = "CRVDEL %d" % crvn
        self._lakeshore.send_cmd(command)

    def _read_mode(self, channel):
        raise NotImplementedError

    def _set_mode(self, channel, mode):
        raise NotImplementedError