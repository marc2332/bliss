# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 331, acessible via Serial line (RS232)

yml configuration example:
#controller:
- class: LakeShore331
  module: temperature.lakeshore.lakeshore331
  name: lakeshore331
  timeout: 3
  serial:
     url: ser2net://lid102:28000/dev/ttyR1
     baudrate: 9600    # max (other possible values: 300, 1200)
     eol: "\r\n"

  inputs:
    - name: ls331_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_331
    - name: ls331_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls331_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls331_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_331
    - name: ls331_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
    - name: ls331_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

  outputs:
    - name: ls331o_1
      channel: 1 
      unit: Kelvin
    - name: ls331o_2
      channel: 2 

  ctrl_loops:
    - name: ls331l_1
      input: $ls331_A
      output: $ls331o_1
      channel: 1
    - name: ls331l_2
      input: $ls331_B
      output: $ls331o_2
      channel: 2
"""
import types
import time
import enum
import re
import os
import sys

from bliss import global_map
from bliss.comm import serial
from bliss.comm.util import get_interface, get_comm
from bliss.common.logtools import log_info, log_debug, log_warning
from bliss.common.utils import autocomplete_property

from bliss.controllers.regulator import Controller
from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreInput as Input
)
from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreOutput as Output
)
from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreLoop as Loop
)

_last_call = time.time()
# limit number of commands per second
# lakeshore 331 supports at most 20 commands per second
def _send_limit(func):
    def f(*args, **kwargs):
        global _last_call
        delta_t = time.time() - _last_call
        if delta_t <= 0.15:
            time.sleep(0.15 - delta_t)
        try:
            return func(*args, **kwargs)
        finally:
            _last_call = time.time()

    return f


class LakeShore331(Controller):

    UNITS = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}
    # IPSENSORUNITS = {1: "volts", 2: "ohms"}

    # Number of calibration curves available
    NCURVES = 41
    NUSERCURVES = (21, 41)
    CURVEFORMAT = {1: "mV/K", 2: "V/K", 3: "Ohms/K", 4: "logOhms/K"}
    CURVETEMPCOEF = {1: "negative", 2: "positive"}

    VALID_INPUT_CHANNELS = ["A", "B"]
    VALID_OUTPUT_CHANNELS = [1, 2]
    VALID_LOOP_CHANNELS = [1, 2]

    @enum.unique
    class SensorTypes(enum.IntEnum):
        Silicon_Diode = 0
        GaAlAs_Diode = 1
        Platinium_250_100_ohm = 2
        Platinium_500_100_ohm = 3
        Platinium_1000_ohm = 4
        NTC_RTD = 5
        Thermocouple_25_mV = 6
        Thermocouple_50_mV = 7
        Sensor_2500_mV_1_mA = 8
        Sensor_7500_mV_1_mA = 9

    @enum.unique
    class Unit(enum.IntEnum):
        KELVIN = 1
        CELSIUS = 2
        SENSOR_UNIT = 3

    @enum.unique
    class Mode(enum.IntEnum):
        MANUAL_PID = 1
        ZONE = 2
        OPEN_LOOP = 3
        AUTO_TUNE_PID = 4
        AUTO_TUNE_PI = 5
        AUTO_TUNE_P = 6

    @enum.unique
    class HeaterRange(enum.IntEnum):
        OFF = 0
        LOW = 1  # 0.5 Watt
        MEDIUM = 2  # 5 Watt
        HIGH = 3  # 50 Watt

    @enum.unique
    class HeaterState(enum.IntEnum):
        OK = 0
        OPEN_LOAD = 1
        SHORT = 2

    def __init__(self, config):

        super().__init__(config)
        self.init_com()
        global_map.register(self._comm, parents_list=[self, "comms"])

    # ------ init methods ------------------------

    def init_com(self):
        self._model_number = 331
        self._comm = get_comm(self.config, parity="O", bytesize=7, stopbits=1)

    def initialize_controller(self):
        """ 
        Initializes the controller.
        """

        log_info(self, "initialize_controller")
        self.clear()

        model = self.model
        if model != self._model_number:
            raise ValueError(
                f"Error, the Lakeshore model is {model}. It should be {self._model_number}."
            )

    def initialize_input(self, tinput):
        """
        Initializes an Input class type object

        Args:
           tinput:  Input class type object          
        """
        log_info(self, "initialize_input")

        input_channel = tinput.config["channel"]
        if input_channel not in self.VALID_INPUT_CHANNELS:
            raise ValueError(
                f"wrong channel '{input_channel}' for the input {tinput}. Should be in {self.VALID_INPUT_CHANNELS}"
            )

        input_unit = tinput.config["unit"]
        if input_unit not in self.UNITS:
            raise ValueError(
                f"wrong unit '{input_unit}' for the input {tinput}. Should be in {self.UNITS}"
            )

    def initialize_output(self, toutput):
        """
        Initializes an Output class type object

        Args:
           toutput:  Output class type object          
        """
        log_info(self, "initialize_output")

        # Note: for Lakeshore models, the output channel is the same as the loop channel.
        output_channel = toutput.config["channel"]
        if output_channel not in self.VALID_OUTPUT_CHANNELS:
            raise ValueError(
                f"wrong channel '{output_channel}' for the output {toutput}. Should be in {self.VALID_OUTPUT_CHANNELS}"
            )

    def initialize_loop(self, tloop):
        """
        Initializes a Loop class type object

        Args:
           tloop:  Loop class type object          
        """
        log_info(self, "initialize_loop")

        # Note: for Lakeshore models, the output channel is the same as the loop channel.
        loop_channel = tloop.config.get("channel")
        output_channel = tloop.output.config["channel"]

        if loop_channel is None:
            loop_channel = tloop.config["channel"] = output_channel

        elif loop_channel != output_channel:
            loop_channel = tloop.config["channel"] = output_channel
            print(
                f"Warning: the loop channel '{loop_channel}' and the channel of its associated output '{output_channel}' are different!"
            )
            print(
                "The output channel will be used and the loop channel will be ignored."
            )

        if loop_channel not in self.VALID_LOOP_CHANNELS:
            raise ValueError(
                f"wrong channel '{loop_channel}' for the loop {tloop}. Should be in {self.VALID_LOOP_CHANNELS}"
            )

        # Get input object channel
        ipch = tloop.input.config["channel"]
        # Get input object unit
        ipu = tloop.input.config["unit"]

        self.set_loop_params(tloop, input_channel=ipch, unit=ipu)

    # ------ get methods ------------------------

    def read_input(self, tinput):
        """Read the current temperature
           Returns:
              (float): current temperature in Kelvin or Celsius 
                       or sensor-unit reading (Ohm or Volt)
                       depending on read_type.
        """
        log_info(self, "read_input: %s" % (tinput))
        input_channel = tinput.channel
        read_unit = tinput.config["unit"]
        if read_unit == "Kelvin":
            try:
                return self._read_temperature(input_channel, "Kelvin")
            except ValueError:
                return float("NAN")
        elif read_unit == "Celsius":
            try:
                return self._read_temperature(input_channel, "Celsius")
            except ValueError:
                return float("NAN")
        elif read_unit == "Sensor_unit":
            try:
                # sensor unit can be Ohm or Volt depending on sensor type
                return self._read_temperature(input_channel, "Sensor_unit")
            except ValueError:
                return float("NAN")

    def read_output(self, toutput):
        """ Read the current value of the output
            Returns:
              (float): the output value as a power percentage
        """
        log_info(self, "read_output: %s" % (toutput))
        return float(toutput.value_percent)

    def state_output(self, toutput):
        """
        Return the state of the Output.

        Args:
           toutput:  Output class type object

        Returns:
           object state as a string. 
        """
        log_info(self, "state_output: %s" % (toutput))
        r = int(self.send_cmd("HTRST?"))
        return self.HeaterState(r)

    # ------ PID methods ------------------------

    def set_kp(self, tloop, kp):
        """ Set the proportional (gain)
            Args:
                tloop:  Loop class type object  
                kp (float): value in 0.1 to 1000
        """
        log_info(self, "set_kp: %s %s" % (tloop, kp))
        self._pid_coeff(tloop.channel, P=kp)

    def get_kp(self, tloop):
        """ Read the proportional (gain)
            Args:
                tloop:  Loop class type object  
            Returns:
                kp (float): value in 0.1 to 1000
        """
        log_info(self, "get_kp: %s" % (tloop))
        kp, ki, kd = self._pid_coeff(tloop.channel)
        return kp

    def set_ki(self, tloop, ki):
        """ Set the integral (reset)
            Args:
                tloop:  Loop class type object  
                ki (float): value in 0.1 to 1000
        """
        log_info(self, "set_ki: %s %s" % (tloop, ki))
        self._pid_coeff(tloop.channel, I=ki)

    def get_ki(self, tloop):
        """ Read the integral (reset)
            Args:
                tloop:  Loop class type object 
            Returns:
                ki (float): value - 0.1 to 1000
        """
        log_info(self, "get_ki: %s" % (tloop))
        kp, ki, kd = self._pid_coeff(tloop.channel)
        return ki

    def set_kd(self, tloop, kd):
        """ Set the derivative (rate)
            Args:
                tloop:  Loop class type object  
                kd (float): value in 0 to 200
        """
        log_info(self, "set_kd: %s %s" % (tloop, kd))
        self._pid_coeff(tloop.channel, D=kd)

    def get_kd(self, tloop):
        """ Read the derivative (rate)
            Args:
                tloop:  Loop class type object
            Returns:
                kd (float): value in 0 to 200
        """
        log_info(self, "get_kd: %s" % (tloop))
        kp, ki, kd = self._pid_coeff(tloop.channel)
        return kd

    def start_regulation(self, tloop):
        """
        Starts the regulation process.

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "start_regulation: %s" % (tloop))

        self._set_loop_on(tloop)

    def stop_regulation(self, tloop):
        """
        Stops the regulation process.

        Args: 
           tloop:  Loop class type object
        """
        log_info(self, "stop_regulation: %s" % (tloop))

        self._set_loop_off(tloop)

    # ------ setpoint methods ------------------------

    def set_setpoint(self, tloop, sp, **kwargs):
        """ Set the setpoint value
            Args:
                tloop:  Loop class type object
                sp (float): the setpoint value
        """
        log_info(self, "set_setpoint: %s %s" % (tloop, sp))
        self.send_cmd("SETP", sp, channel=tloop.channel)

    def get_setpoint(self, tloop):
        """ Get the setpoint value
            Args:
                tloop:  Loop class type object
            Returns:
                (float): the setpoint value
        """
        log_info(self, "get_setpoint: %s" % (tloop))
        return float(self.send_cmd("SETP?", channel=tloop.channel))

    # ------ setpoint ramping methods ------------------------

    def start_ramp(self, tloop, sp, **kwargs):
        """ Start ramping to setpoint
            Args:
                tloop:  Loop class type object
                sp (float): the setpoint value
            Kwargs:
                rate (float): ramp rate [K/min], values 0.1 to 100 with 0.1 resolution
        """
        log_info(self, "start_ramp: %s %s" % (tloop, sp))

        rate = kwargs.get("rate")

        if rate is None:
            rate = self.get_ramprate(tloop)

        # self.set_setpoint(tloop, sp)  # before ???
        self.send_cmd("RAMP", 1, rate, channel=tloop.channel)
        self.set_setpoint(tloop, sp)  # or after ???

    def stop_ramp(self, tloop):
        """ Stop ramping to setpoint
            Args:
                tloop:  Loop class type object
        """
        log_info(self, "stop_ramp: %s" % (tloop))
        # if ramp is active, disable it
        if self.is_ramping_enabled(tloop):
            # setting ramp rate causes ramping off
            rate = self.get_ramprate(tloop)
            self.send_cmd(
                "RAMP", 0, rate, channel=tloop.channel
            )  # 0 means 'set ramping OFF'

    def is_ramping(self, tloop):
        """
        Get the ramping status. 
        Status is True if the current setpoint is ramping to 
        the target setpoint (the one set by user with self.set_setpoint(tloop, sp) )

        Args:
           tloop:  Loop class type object

        Returns:
           (bool) True if ramping, else False.
        """
        log_info(self, "is_ramping: %s" % (tloop))

        if not self.is_ramping_enabled(tloop):
            # the ramping is disabled
            return False

        ramp_stat = self.send_cmd("RAMPST?", channel=tloop.channel)
        if int(ramp_stat) == 1:
            return True
        else:
            return False

    def set_ramprate(self, tloop, rate):
        """ Set the ramp rate
            Args:
                tloop:  Loop class type object
                rate (float): The ramp rate [K/min] - no action, cash value only.
        """
        log_info(self, "set_ramprate: %s %s" % (tloop, rate))

        if rate < 0.1 or rate > 100:
            raise ValueError("Ramp value %s is out of bounds [0.1,100]" % rate)
        # self.send_cmd("RAMP", 0, rate, channel=tloop.channel) # this would make the ramping off when setting a new ramprate
        self.send_cmd("RAMP", 1, rate, channel=tloop.channel)

    def get_ramprate(self, tloop):
        """ Read the ramp rate
            Args:
               tloop:  Loop class type object
            Returns:
               (float): ramprate [K/min]
        """
        log_info(self, "get_ramprate: %s" % (tloop))
        r = self.send_cmd("RAMP?", channel=tloop.channel).split(",")
        return float(r[1])

    # ------ raw methods (optional) ------------------------

    def Wraw(self, string):
        """ Write a string to the controller
            Args:
                string The complete raw string to write (except eol)
                Normaly will use it to set a/some parameter/s in 
                the controller.
        """
        log_info(self, "Wraw")
        log_debug(self, "command to send = {0}".format(string))
        cmd = string + self.eol
        self._comm.write(cmd.encode())

    def Rraw(self):
        """ Read a string from the controller
            Returns:
                response from the controller
        """
        log_info(self, "Rraw")
        cmd = self.eol
        asw = self._comm.readline(cmd.encode())
        log_debug(self, "raw answer = {0}".format(asw))
        return asw.decode()

    def WRraw(self, string):
        """ Write a string to the controller and then reading answer back
            Args:
               string: the complete raw string to write (except eol)
            Returns:
               response from the controller
        """
        log_info(self, "WRraw")
        log_debug(self, "command to send = {0}".format(string))
        cmd = string + self.eol
        asw = self._comm.write_readline(cmd.encode())
        log_debug(self, "raw answer = {0}".format(asw))
        return asw.decode()

    # ------ safety methods (optional) ------------------------------

    def set_in_safe_mode(self, toutput):
        """
            Set the output in a safe mode (like stop heating)

            Args:
                toutput:  Output class type object 
        """
        log_info(self, "set_in_safe_mode: %s" % (toutput))

        toutput.range = 0

    # ----- controller specific methods -----------------

    @_send_limit
    def send_cmd(self, command, *args, channel=None):
        """ Send a command to the controller
            Args:
                command (str): The command string
                args: Possible variable number of parameters
                channel: input or loop channel (depending on the cmd) 
            Returns:
                Answer from the controller if ? in the command
        """
        log_info(self, "send_cmd")
        # log_debug(self, "command = {0}, channel = {1})".format(command, channel))
        if channel is None:
            values = "".join(str(x) for x in args)
            cmd = f"{command} {values}"
        else:
            values = ",".join(str(x) for x in args)
            if len(values) == 0:
                cmd = f"{command} {channel}"
            else:
                cmd = f"{command} {channel},{values}"
        # log_debug(self, "values = {0}".format(values))
        log_debug(self, f"send_cmd {cmd}")
        if "?" in command:
            asw = self._comm.write_readline(cmd.encode() + self.eol.encode())
            return asw.decode().strip(";")
        else:
            self._comm.write(cmd.encode() + self.eol.encode())

    @property
    def eol(self):
        return self._comm._eol

    @property
    def model(self):
        """ Get the model number
            Returns:
                model (int): model number
        """
        log_info(self, "model")
        model = self.send_cmd("*IDN?").split(",")[1]
        return int(model[5:8])

    def clear(self):
        """ Clears the bits in the Status Byte, Standard Event and Operation
            Event Registers. Terminates all pending operations.
        """
        self.send_cmd("*CLS")

    def alarm_reset(self):
        """ Clears both the high and low status of all alarms
            Args:
                None (though this command does not need even the input
                    channel, we put it here since alarms are related
                    to the state on input like for ex. measured temperature
                    above alarm high-limit etc)
        """
        log_info(self, "alarm_reset")
        self.send_cmd("ALMRST")

    def show(self, name=None):
        """ Display all main parameters and values for the temperature controller
            Prints:
                device ID, PID, heater range, loop status, sensors configuration, inputs temperature etc.
        """
        repr_list = []
        log_info(self, "Controller:show")
        # Get full identification string
        full_id = self.send_cmd("*IDN?")
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

            sensor_type_dict = sensor.sensor_type
            stp = sensor_type_dict.get("sensor_type")
            stp = self.SensorTypes(stp).name
            scp = sensor_type_dict.get("compensation")
            scp = "On" if scp else "Off"
            repr_list.append("Sensor type: %s, Compensation: %s" % (stp, scp))
            repr_list.append(
                "Temperature: %.3f %s" % (sensor.read(), sensor.config.get("unit"))
            )
        # outputs
        output = self.outputs.get(name)
        if output is not None:
            repr_list.append(f"\nOutput {name} :\n{'='*(len(name)+9)}")
            repr_list.append("Heater range is %s" % output.range.name)
            # Get heater status
            repr_list.append("Heater status is %s" % self.state_output(output).name)
            # Get heater power
            htr_power = float(output.value_percent)
            repr_list.append("Heater power = %.1f %%" % htr_power)

        # loops
        loop = self.loops.get(name)
        if loop is not None:
            repr_list.append(f"\nLoop {name} :\n{'='*(len(name)+7)}")
            params_dict = self.get_loop_params(loop)
            repr_list.append("Controlled by sensor %(input)s in %(unit)s" % params_dict)
            repr_list.append("Temp. control is set to %s" % loop.mode.name)
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

    ## --- input methods --------
    def get_sensor_type(self, tinput):
        """ Read input type parameters

            Args:
                tinput:  Input class type object
                
            Returns:
                dict: {sensor_type: (int), compensation: (int) }

        """
        log_info(self, "get_sensor_type")
        asw = self.send_cmd("INTYPE?", channel=tinput.channel).split(",")
        return {"sensor_type": int(asw[0]), "compensation": int(asw[1])}

    def set_sensor_type(self, tinput, sensor_type, compensation):
        """ Set input type parameters

            Args:
                tinput:  Input class type object
                sensor_type   (int): see 'SensorTypes'
                compensation  (int): 0=off or 1=on

            <compensation> Specifies input compensation where 0 = off and 1 = on.
            Reversal for thermal EMF compensation if input is resistive, room compensation if input is thermocouple.
            Always 0 if input is a diode.    
            
        """
        log_info(self, "set_sensor_type")
        self.send_cmd("INTYPE", sensor_type, compensation, channel=tinput.channel)

    def get_filter_params(self, tinput):
        """ Read the input filter parameters
            Args:
                tinput:  Input class type object

            Returns:
                dict{
                    onoff  (int): specifies whether the filter function is 1 = ON or 0 = OFF
                    points (int): specifies how many data points the filtering function
                                uses. Valid range = 2 to 64.
                    window (int): specifies what percent of full scale reading
                                limits the filtering function. Reading changes
                                greater than this percentage reset the filter.
                    }
        """

        log_info(self, "get_filter_params")

        asw = self.send_cmd("FILTER?", channel=tinput.channel).split(",")
        return {"onoff": int(asw[0]), "points": int(asw[1]), "window": int(asw[2])}

    def set_filter_params(self, tinput, **kwargs):
        """ Set the input filter parameters
            Args:
                tinput:  Input class type object

            Kwargs:
                onoff  (int): specifies whether the filter function is 1 = ON or 0 = OFF
                points (int): specifies how many data points the filtering function
                              uses. Valid range = 2 to 64.
                window (int): specifies what percent of full scale reading
                              limits the filtering function. Reading changes
                              greater than this percentage reset the filter.
                              Valid range: 1 to 10%.
        """
        log_info(self, "set_filter_params")

        onoff = kwargs.get("onoff")
        points = kwargs.get("points")
        window = kwargs.get("window")

        current_params = self.get_filter_params(tinput)

        if onoff is None:
            onoff = current_params["onoff"]

        if points is None:
            points = current_params["points"]
        elif points not in range(2, 65):
            raise ValueError(
                "Error, the nb of points {0} is not in range 2 to 64.".format(points)
            )

        if window is None:
            window = current_params["window"]
        elif window not in range(1, 11):
            raise ValueError(
                "Error, the filter windows {0} is not in range 1 to 10 percent.".format(
                    window
                )
            )

        self.send_cmd("FILTER", onoff, points, window, channel=tinput.channel)

    def alarm_status(self, tinput):
        """ Shows high and low alarm state for given input
            Args:
                tinput:  Input class type object 
            Returns:
                tuple (str, str): high and low alarm state 'On' or 'Off'
        """
        log_info(self, "alarm_status")
        asw = self.send_cmd("ALARMST?", channel=tinput.channel).split(",")
        hist = "On" if int(asw[0]) == 1 else "Off"
        lost = "On" if int(asw[1]) == 1 else "Off"
        log_debug(self, "Alarm high state = %s" % hist)
        log_debug(self, "Alarm Low  state = %s" % lost)
        return (hist, lost)

    ## --- output methods --------
    def read_value_percent(self, touput):
        """ return ouptut current value as a percentage (%)
            args:
                touput:  Output class type object 
        """
        log_info(self, "read_value_percent")
        if int(touput.channel) == 1:
            return self.send_cmd("HTR?")
        elif int(touput.channel) == 2:
            return self.send_cmd("AOUT?")
        else:
            raise ValueError(
                f"Wrong output channel: '{touput.channel}' should be in {self.VALID_OUTPUT_CHANNELS} "
            )

    def get_heater_range(self, touput):
        """ Read the heater range
            args:
                touput:  Output class type object 
            returns: 
                the heater range (see self.HeaterRange)
        """
        log_info(self, "get_heater_range")
        r = int(self.send_cmd("RANGE?"))
        return self.HeaterRange(r)

    def set_heater_range(self, touput, value):
        """ Set the heater range (see self.HeaterRange)
            It is used for heater output 1 (= loop 1), while for
            output 2 (=loop 2) can choose only between 0(heater off) and 1(heater on)
            
            args:
                - touput:  Output class type object 
                - value (int): The value of the range
        """
        log_info(self, "set_heater_range")
        v = self.HeaterRange(value).value
        self.send_cmd("RANGE", v)

    ## --- loop methods --------
    def get_loop_mode(self, tloop):
        """ return the control loop mode 
            args:
                - tloop:  Loop class type object
            returns:
                one of the self.Mode enum
        """
        log_info(self, "get_loop_mode")
        return self.Mode(int(self.send_cmd("CMODE?", channel=tloop.channel)))

    def set_loop_mode(self, tloop, mode):
        """ set the mode for the loop control 
            args:
                - tloop:  Loop class type object
                - mode (int): see self.Mode enum
        """
        log_info(self, "set_loop_mode")
        value = self.Mode(mode).value
        self.send_cmd("CMODE", value, channel=tloop.channel)

    def get_loop_unit(self, tloop):
        """ get the units used for the loop setpoint 
            args:
                tloop:  Loop class type object
            returns: 
                the unit (see self.Unit)
        """
        log_info(self, "get_loop_units")
        asw = self.send_cmd("CSET?", channel=tloop.channel).split(",")
        unit = int(asw[1])
        return self.Unit(unit)

    def set_loop_unit(self, tloop, unit):
        """ set the units used for the loop setpoint 
            args:
                - tloop:  Loop class type object
                - unit (int): the unit type, see 'Unit' enum
        """

        log_info(self, "set_loop_units")
        asw = self.send_cmd("CSET?", channel=tloop.channel).split(",")
        value = self.Unit(unit).value
        self.send_cmd("CSET", asw[0], value, asw[2], asw[3], channel=tloop.channel)

    def get_loop_params(self, tloop):
        """ Read Control Loop Parameters
            Args:
                tloop:  Loop class type object
            Returns:
                dict: {'input'   (str): the associated input channel, see 'VALID_INPUT_CHANNELS'
                       'unit'    (str): the loop setpoint units, could be Kelvin(1), Celsius(2) or Sensor_unit(3)
                       'powerup' (str): specifies whether the control loop is ON(=1) or OFF(=0) after power-up
                       'currpow' (str): specifies whether the heater output displays in current(=1) or power(=2)
                      }
        """

        log_info(self, "get_loop_params")
        asw = self.send_cmd("CSET?", channel=tloop.channel).split(",")
        input_chan = asw[0]
        unit = self.REVUNITS[int(asw[1])]
        powerup = "ON" if int(asw[2]) == 1 else "OFF"
        currpow = "current" if int(asw[3]) == 1 else "power"
        return {
            "input": input_chan,
            "unit": unit,
            "powerup": powerup,
            "currpow": currpow,
        }

    def set_loop_params(self, tloop, input_channel=None, unit=None):
        """ Set Control Loop Parameters
            Args:
                tloop:  Loop class type object
                input_channel (str): see 'VALID_INPUT_CHANNELS'
                unit          (str): the loop setpoint unit, could be 'Kelvin', 'Celsius', 'Sensor_unit'
            
            Remark: In this method we do not pass 2 further arguments:
                  
                  - 'powerup' is set to 0 as default, which
                    means that the control loop is off after powerup. This
                    is the default value and the logic is consistent with
                    the one for models 336 and 340.

                  - 'currpow' is set to 1 as default, which
                    means that the heater output display current(=1) instead of power(=2)
        """
        log_info(self, "set_loop_params")
        inputc, unitc, powerupc, currpowc = self.send_cmd(
            "CSET?", channel=tloop.channel
        ).split(",")
        if input_channel is None:
            input_channel = inputc
        if unit is None:
            unit = unitc
        elif unit not in self.UNITS:
            raise ValueError(
                f"Error: acceptables values for unit are { ', '.join(self.UNITS.keys()) }"
            )
        else:
            unit = self.UNITS[unit]

        # self.send_cmd(
        #    "CSET", input_channel, unit, powerupc, currpowc, channel=loop_channel
        # )  # use current value for powerup and currpow
        self.send_cmd(
            "CSET", input_channel, unit, 0, 1, channel=tloop.channel
        )  # force using default powerup and currpow

    def is_ramping_enabled(self, tloop):
        """ return if the ramping capacity is Enabled or Disabled """

        r = self.send_cmd("RAMP?", channel=tloop.channel).split(",")
        if int(r[0]) == 1:
            return True
        else:
            return False

    ## ----- Curve management ----------------------------

    def used_curve(self, input_channel):
        """ return the curve parameters associated to an input_channel
            args:
                - input_channel (str): see 'VALID_INPUT_CHANNELS'
            returns: 
                dict {
                    "curve_number": (int),
                    "curve_name"  : (str),
                    "curve_sn"    : (str),
                    "curve_format": (str),
                    "curve_temperature_limit": (str),
                    "curve_temperature_coefficient": (str)
                }
        """

        log_info(self, "used_curve")
        curve_number = self.send_cmd("INCRV?", channel=input_channel)
        command = "CRVHDR? %s" % curve_number
        curve_header = self.send_cmd(command)
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

    def select_curve(self, crvn, input_channel):
        """ specifies the curve an input uses for temperature conversion
            args:
                - crvn (int): curve number: 0 = None, 1-20= standard curves, 21-41= user curves
                - input_channel (str): see 'VALID_INPUT_CHANNELS'
        """

        log_info(self, f"select_curve: {crvn}")
        if crvn not in range(1, self.NCURVES + 1):
            raise ValueError(
                f"Curve number {crvn} is invalid. Should be in [1,{self.NCURVES}]"
            )
        else:
            self.send_cmd("INCRV", crvn, channel=input_channel)

    def show_all_curves(self):
        """ Prints all the available curves information
        """
        log_info(self, "list_all_curves")
        print(" #            Name       SN         Format     Limit(K) Temp. coef.")
        for i in range(1, self.NCURVES + 1):
            command = "CRVHDR? %s" % i
            curve_header = self.send_cmd(command)
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

    def write_curve(self, crvn, crvfile):
        log_info(self, "write_curve")
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
        loaded_curve = self.send_cmd(command)
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
        self.send_cmd(command)
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
                        self.send_cmd(command)
                        breakpts += 1
        if breakpts == int(curve_nb_breakpts):
            print(
                "\nCurve %d has been written into the LakeShore model 331 temperature controller."
                % crvn
            )
            # Reading back for checking the header
            command = "CRVHDR? %d" % crvn
            curve_header = self.send_cmd(command)
            print("The header read back for the %d is:" % crvn)
            print(curve_header)
            if self.model == 340:
                print("Updating the curve flash with the current user curves.")
                print("May take several seconds.")
                self.send_cmd("CRVSAV")
        else:
            print(
                "Error. The number of breakpoints written (%d) does not match with %d."
                % (breakpts, int(curve_nb_breakpts))
            )

    def delete_curve(self, crvn):
        log_info(self, f"delete_curve:{crvn}")
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
        self.send_cmd(command)

    ## ----- private methods -------------------------

    def _set_loop_on(self, tloop):
        log_info(self, "_set_loop_on")
        if tloop.output.range == self.HeaterRange.OFF:
            tloop.output.range = self.HeaterRange.LOW.value  # LOW = 1

    def _set_loop_off(self, tloop):
        log_info(self, "_set_loop_off")
        tloop.output.range = self.HeaterRange.OFF.value  # OFF = 0

    def _read_temperature(self, input_channel, unit):
        """ Read the current temperature
            Args:
              input_channel (str): see 'VALID_INPUT_CHANNELS'
              unit (str): temperature unit for reading: Kelvin or Celsius
                           or Sensor_unit
            Returns:
              (float): current temperature
        """
        log_info(self, "_read_temperature")
        # Query Input Status before reading temperature
        # If status is OK, then read the temperature
        asw = int(self.send_cmd("RDGST?", channel=input_channel))
        if asw == 0:
            if unit == "Kelvin":
                return float(self.send_cmd("KRDG?", channel=input_channel))
            elif unit == "Celsius":
                return float(self.send_cmd("CRDG?", channel=input_channel))
            elif unit == "Sensor_unit":
                return float(self.send_cmd("SRDG?", channel=input_channel))
        if asw & 16:
            log_warning(self, "Temperature UnderRange on input %s" % input_channel)
            raise ValueError("Temperature value on input %s is invalid" % input_channel)
        if asw & 32:
            log_warning(self, "Temperature OverRange on input %s" % input_channel)
            raise ValueError("Temperature value on input %s is invalid" % input_channel)
        if asw & 64:
            log_warning(
                self, "Temperature in Sensor_unit = 0 on input %s" % input_channel
            )
            raise ValueError(
                "Temperature in Sensor_unit = 0 on input %s" % input_channel
            )
        if asw & 128:
            log_warning(
                self, "Temperature OverRange in Sensor_unit on input %s" % input_channel
            )
            raise ValueError(
                "Temperature OverRange in Sensor_unit on input %s" % input_channel
            )
        raise RuntimeError("Could not read temperature on channel %s" % input_channel)

    def _pid_coeff(self, loop_channel, **kwargs):
        """ Read/Set Control Loop PID Values (P, I, D)
            Args:
              loop_channel  (int): see 'VALID_LOOP_CHANNELS'
              P (float): Proportional gain (0.1 to 1000), None if read
              I (float): Integral reset (0.1 to 1000) [value/s], None if read
              D (float): Derivative rate (0 to 200) [%], None if read
            Returns:
              None if set
              p (float): P
              i (float): I
              d (float): D
        """
        log_info(self, "pid")
        kp = kwargs.get("P")
        ki = kwargs.get("I")
        kd = kwargs.get("D")
        if len(kwargs):
            kpc, kic, kdc = self.send_cmd("PID?", channel=loop_channel).split(",")
            if kp is None:
                kp = kpc
            if ki is None:
                ki = kic
            if kd is None:
                kd = kdc

            if float(kp) < 0.1 or float(kp) > 1000.:
                raise ValueError(
                    "Proportional gain %s is out of bounds [0.1,1000]" % kp
                )
            if float(ki) < 0.1 or float(ki) > 1000.:
                raise ValueError("Integral reset %s is out of bounds [0.1,1000]" % ki)
            if float(kd) < 0 or float(kd) > 200:
                raise ValueError("Derivative rate %s is out of bounds [0,200]" % kd)
            self.send_cmd("PID", kp, ki, kd, channel=loop_channel)

        else:
            kp, ki, kd = self.send_cmd("PID?", channel=loop_channel).split(",")
            return float(kp), float(ki), float(kd)
