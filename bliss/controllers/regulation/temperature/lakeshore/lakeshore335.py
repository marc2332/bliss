# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 335, acessible via GPIB or USB

yml configuration example:
#controller:
- class: LakeShore335
  module: temperature.lakeshore.lakeshore335
  name: lakeshore335
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 9 
  usb:
     url: ser2net://lid102:28000/dev/ttyUSB0
     # when not in model 331 or model 332 emulation mode,
     # baud-rate of 57600 is the only one possible. If configured
     # in emulation mode, then can have also 300, 1200, 9600
     # as possible values for baud-rate.
     baudrate: 57600
  inputs:
    - name: ls335_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_335
    - name: ls335_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls335_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls335_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_335
    - name: ls335_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
    - name: ls335_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

  outputs:
    - name: ls335o_1
      channel: 1 
      unit: Kelvin
    - name: ls335o_2
      channel: 2 

  ctrl_loops:
    - name: ls335l_1
      input: $ls335_A
      output: $ls335o_1
      channel: 1
    - name: ls335l_2
      input: $ls335_B
      output: $ls335o_2
      channel: 2
"""

import time
import enum

from bliss.shell.standard import ShellStr

from bliss.comm.util import get_comm
from bliss.common.logtools import log_info
from bliss.common.regulation import lazy_init

from bliss.controllers.regulation.temperature.lakeshore.lakeshore331 import LakeShore331
from bliss.controllers.regulation.temperature.lakeshore.lakeshore import LakeshoreInput

from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreOutput as Output
)
from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreLoop as Loop
)


_last_call = time.time()
# limit number of commands per second
# lakeshore 335 supports at most 20 commands per second
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


class Input(LakeshoreInput):
    @lazy_init
    def set_sensor_type(
        self, sensor_type, autorange=1, srange=0, compensation=0, units=None
    ):
        """ set the sensor type 
            Args:
                sensor_type   (int): see 'valid_sensor_types'
                autorange     (int): 0=off or 1=on                                      (not applied for Thermocouple and Diode, use 0)
                range         (int): see 'valid_sensor_type_ranges' (when autorange is off)  (not applied for Thermocouple, use 0)
                compensation  (int): 0=off or 1=on                                      (not applied for Diode, use 0)
                units         (int): specifies units for sensor reading and setpoint (see 'UNITS')

            <compensation> Specifies input compensation where 0 = off and 1 = on.
            Reversal for thermal EMF compensation if input is resistive, room compensation if input is thermocouple.
            Always 0 if input is a diode. 
        """
        self.controller.set_sensor_type(
            self, sensor_type, autorange, srange, compensation, units
        )

    @property
    def valid_sensor_type_ranges(self):
        lines = ["\n"]
        for stp in self.controller.SENSOR_TYPE_RANGES:
            lines.append(f"=== Sensor type: {stp} ===")
            for sr, sn in self.controller.SENSOR_TYPE_RANGES[stp].items():
                lines.append(f"{sr} = {sn}")
            lines.append("\n")

        return ShellStr("\n".join(lines))


class LakeShore335(LakeShore331):

    UNITS = {"Kelvin": 1, "Celsius": 2, "Sensor unit": 3}
    REVUNITS = {1: "Kelvin", 2: "Celsius", 3: "Sensor unit"}
    # IPSENSORUNITS = {1: "volts", 2: "ohms"}
    NUMINPUT = {1: "A", 2: "B"}
    REVINPUT = {"A": 1, "B": 2}

    NCURVES = 59
    NUSERCURVES = (21, 59)
    CURVEFORMAT = {1: "mV/K", 2: "V/K", 3: "Ohms/K", 4: "logOhms/K"}
    CURVETEMPCOEF = {1: "negative", 2: "positive"}

    VALID_INPUT_CHANNELS = ["A", "B"]
    VALID_OUTPUT_CHANNELS = [1, 2]
    VALID_LOOP_CHANNELS = [1, 2]

    @enum.unique
    class SensorTypes(enum.IntEnum):
        Disabled = 0
        Diode = 1
        Platinium_RTD = 2
        NTC_RTD = 3
        Thermocouple = 4

    SENSOR_TYPE_RANGES = {
        "Diode": {"2.5V": 0, "10V": 1},
        "Platinium_RTD": {
            "10ohm": 0,
            "30ohm": 1,
            "100ohm": 2,
            "300ohm": 3,
            "1000ohm": 4,
            "3000ohm": 5,
            "10000ohm": 6,
        },
        "NTC_RTD": {
            "10ohm": 0,
            "30ohm": 1,
            "100ohm": 2,
            "300ohm": 3,
            "1000ohm": 4,
            "3000ohm": 5,
            "10000ohm": 6,
            "30000ohm": 7,
            "100000ohm": 8,
        },
        "Thermocouple": {"50mV": 0},
    }

    @enum.unique
    class Mode(enum.IntEnum):
        OFF = 0
        CLOSED_LOOP_PID = 1
        ZONE = 2
        OPEN_LOOP = 3
        MONITOR_OUT = 4
        WARMUP_SUPPLY = 5

    @enum.unique
    class HeaterRange(enum.IntEnum):
        OFF = 0
        LOW = 1  # 0.5 Watt
        MEDIUM = 2  # 5 Watt
        HIGH = 3  # 50 Watt

        # Note: for output 2 in Voltage mode: 0=Off, 1=On

    def init_com(self):
        self._model_number = 335
        if "serial" in self.config:
            self._comm = get_comm(
                self.config, baudrate=57600, parity="O", bytesize=7, stopbits=1
            )
        else:
            self._comm = get_comm(self.config)

    def state_output(self, toutput):
        """
        Return the state of the Output.

        Args:
           toutput:  Output class type object

        Returns:
           object state as a string. 
        """
        log_info(self, "state_output: %s" % (toutput))
        r = int(self.send_cmd("HTRST?", channel=toutput.channel))
        return self.HeaterState(r)

    def read_value_percent(self, touput):
        """ return ouptut current value as a percentage (%)
            args:
                touput:  Output class type object
        """
        log_info(self, "read_value_percent")
        return self.send_cmd("HTR?", channel=touput.channel)

    def get_sensor_type(self, tinput):
        """ Read input type parameters

            Args:
                tinput:  Input class type object
                
            Returns:
                dict: {sensor_type: (int), autorange: (int), range: (int), compensation: (int), units: (int) }

        """
        log_info(self, "get_sensor_type")
        asw = self.send_cmd("INTYPE?", channel=tinput.channel).split(",")
        return {
            "sensor_type": int(
                asw[0]
            ),  # sname  = self.SensorTypes(int(asw[0])).name.strip()
            "autorange": int(
                asw[1]
            ),  # srange = self.SENSOR_TYPE_RANGES[sname][int(asw[2])]
            "range": int(asw[2]),
            "compensation": int(asw[3]),
            "units": int(asw[4]),  # self.REVUNITS[int(asw[4])]
        }

    def set_sensor_type(
        self, tinput, sensor_type, autorange, srange, compensation, units
    ):
        """ Set input type parameters

            Args:
                tinput:  Input class type object
                sensor_type   (int): see 'SensorTypes'
                autorange     (int): 0=off or 1=on                                      (not applied for Thermocouple and Diode, use 0)
                range         (int): see 'SENSOR_TYPE_RANGES'  (when autorange is off)  (not applied for Thermocouple, use 0)
                compensation  (int): 0=off or 1=on                                      (not applied for Diode, use 0)
                units         (int): specifies units for sensor reading and setpoint

            <compensation> Specifies input compensation where 0 = off and 1 = on.
            Reversal for thermal EMF compensation if input is resistive, room compensation if input is thermocouple.
            Always 0 if input is a diode.    
            
        """
        log_info(self, "set_sensor_type")

        if autorange == 1:
            srange = 0

        if units is None:
            units = tinput.config["unit"]

        self.send_cmd(
            "INTYPE",
            sensor_type,
            autorange,
            srange,
            compensation,
            units,
            channel=tinput.channel,
        )

    def get_heater_range(self, touput):
        """ Read the heater range
            args:
                touput:  Output class type object 
            returns: the heater range (see self.HeaterRange)
        """
        log_info(self, "get_heater_range")
        r = int(self.send_cmd("RANGE?", channel=touput.channel))
        return self.HeaterRange(r)

    def set_heater_range(self, touput, value):
        """ Set the heater range (see self.HeaterRange)
            It is used for heater output 1 (= loop 1), while for
            output 2 (=loop 2) in Voltage mode, can choose only between 0(heater off) and 1(heater on)
            args:
                - touput:  Output class type object 
                - value (int): The value of the range
        """
        log_info(self, "set_heater_range")
        v = self.HeaterRange(value).value
        self.send_cmd("RANGE", v, channel=touput.channel)

    def get_loop_mode(self, tloop):
        """ return the control loop mode 
            args:
                - tloop:  Loop class type object
            returns:
                one of the self.Mode enum
        """
        log_info(self, "get_loop_mode")
        asw = self.send_cmd("OUTMODE?", channel=tloop.channel).split(",")
        return self.Mode(int(asw[0]))

    def set_loop_mode(self, tloop, mode):
        """ set the mode for the loop control 
            args:
                - tloop:  Loop class type object
                - mode (int): see self.Mode enum
        """
        log_info(self, "set_loop_mode")
        value = self.Mode(mode).value
        asw = self.send_cmd("OUTMODE?", channel=tloop.channel).split(",")
        self.send_cmd("OUTMODE", value, asw[1], asw[2], channel=tloop.channel)

    def get_loop_unit(self, tloop):
        """ get the units used for the loop setpoint 
            args:
                - tloop:  Loop class type object
            returns: the unit (see self.Unit)
        """
        log_info(self, "get_loop_unit")
        asw = self.send_cmd("INTYPE?", channel=tloop.input.channel).split(",")
        unit = int(asw[4])
        return self.Unit(unit)

    def set_loop_unit(self, tloop, unit):
        """ set the units used for the loop setpoint 
            args:
                - tloop:  Loop class type object
                - unit (int): the unit type, see 'Unit' enum
        """

        log_info(self, "set_loop_unit")
        asw = self.send_cmd("INTYPE?", channel=tloop.input.channel).split(",")
        value = self.Unit(unit).value
        self.send_cmd(
            "INTYPE", asw[0], asw[1], asw[2], asw[3], value, channel=tloop.input.channel
        )

    def get_loop_params(self, tloop):
        """ Read Control Loop Parameters
            Args:
                tloop:  Loop class type object
            
            Returns:
                dict: {'input'   (str): the associated input channel, see 'VALID_INPUT_CHANNELS'
                       'unit'    (str): the loop setpoint units, could be Kelvin(1), Celsius(2) or Sensor_unit(3)
                       'powerup' (str): specifies whether the control loop is ON(=1) or OFF(=0) after power-up
                       'currpow' (str): not used
                      }
        """
        log_info(self, "get_loop_params")
        asw = self.send_cmd("OUTMODE?", channel=tloop.channel).split(",")
        inpch = self.NUMINPUT[int(asw[1])]  # inpch = 'A' or 'B'
        powerup = "ON" if int(asw[2]) == 1 else "OFF"

        asw = self.send_cmd("INTYPE?", channel=inpch).split(",")
        unit = self.REVUNITS[int(asw[4])]
        currpow = "N/A"
        return {"input": inpch, "unit": unit, "powerup": powerup, "currpow": currpow}

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

        modec, inputc, powerupc = self.send_cmd(
            "OUTMODE?", channel=tloop.channel
        ).split(",")
        if input_channel is None:
            input_channel = self.NUMINPUT[
                int(inputc)
            ]  # input_channel as a string 'A' or 'B'

        sensor_typec, autorangec, rangec, compensationc, unitc = self.send_cmd(
            "INTYPE?", channel=input_channel
        ).split(",")

        if unit is None:
            unit = int(unitc)
        elif unit != "Kelvin" and unit != "Celsius" and unit != "Sensor_unit":
            raise ValueError(
                "Error: acceptables values for unit are 'Kelvin' or 'Celsius' or 'Sensor_unit'."
            )
        else:
            unit = self.UNITS[unit]  # unit as an integer

        self.send_cmd("OUTMODE", modec, input_channel, powerupc, channel=tloop.channel)
        self.send_cmd(
            "INTYPE",
            sensor_typec,
            autorangec,
            rangec,
            compensationc,
            unit,
            channel=input_channel,
        )
