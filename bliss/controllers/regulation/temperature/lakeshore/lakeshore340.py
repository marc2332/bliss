# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 340, acessible via GPIB or Serial line (RS232)

yml configuration example:
#controller:
- class: LakeShore340
  module: temperature.lakeshore.lakeshore340
  name: lakeshore340
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 9 
  serial:
     url: ser2net://lid102:28000/dev/ttyR1
     baudrate: 19200    # max (other possible values: 300, 1200,
                        #                      2400, 4800, 9600)
  inputs:
    - name: ls340_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_340
    - name: ls340_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls340_A_su  # in Sensor_unit (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls340_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_340
    - name: ls340_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
    - name: ls340_B_su  # in Sensor_unit (Ohm or Volt)
      channel: B
      unit: Sensor_unit

  outputs:
    - name: ls340o_1
      channel: 1 

    - name: ls340o_2
      channel: 2 

  ctrl_loops:
    - name: ls340l_1
      input: $ls340_A
      output: $ls340o_1
      channel: 1
    - name: ls340l_2
      input: $ls340_B
      output: $ls340o_2
      channel: 2
"""

import time
import enum

from bliss.shell.standard import ShellStr

from bliss.common.regulation import lazy_init
from bliss.common.logtools import log_info
from bliss.comm.util import get_comm

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
# lakeshore 340 supports at most 20 commands per second
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
        self, sensor_type, units=None, coefficient=None, excitation=None, srange=None
    ):
        """ Set input type parameters

            Args:
                sensor_type   (int): see 'SensorTypes'
                units         (int): specifies input sensor units [ 0=special, 1=volts, 2=ohms ]
                coefficient   (int): specifies input coefficient [ 0=special, 1=negative, 2=positive ]
                excitation    (int): specifies input excitation  [ 0 to 12] (see 'valid_sensor_excitation')
                srange        (int): specifies the input range   [ 1 to 13 ] (see 'valid_sensor_range')
            
        """
        self.controller.set_sensor_type(
            self, sensor_type, units, coefficient, excitation, srange
        )

    @property
    def valid_sensor_excitation(self):
        lines = ["\n"]
        for stn, sts in self.controller.SENSOR_EXCITATION.items():
            lines.append(f"{sts} = {stn}")

        return ShellStr("\n".join(lines))

    @property
    def valid_sensor_range(self):
        lines = ["\n"]
        for stn, sts in self.controller.SENSOR_RANGE.items():
            lines.append(f"{sts} = {stn}")

        return ShellStr("\n".join(lines))


class LakeShore340(LakeShore331):

    NCURVES = 60
    NUSERCURVES = (21, 60)
    CURVEFORMAT = {1: "mV/K", 2: "V/K", 3: "Ohms/K", 4: "logOhms/K"}
    CURVETEMPCOEF = {1: "negative", 2: "positive"}

    SENSOR_EXCITATION = {
        0: "Off",
        1: "30nA",
        2: "100nA",
        3: "300nA",
        4: "1uA",
        5: "3uA",
        6: "10uA",
        7: "30uA",
        8: "100uA",
        9: "300uA",
        10: "1mA",
        11: "10mV",
        12: "1mV",
    }

    SENSOR_RANGE = {
        1: "1mV",
        2: "2.5mV",
        3: "5mV",
        4: "10mV",
        5: "25mV",
        6: "50mV",
        7: "100mV",
        8: "250mV",
        9: "500mV",
        10: "1V",
        11: "2.5V",
        12: "5V",
        13: "7.5V",
    }

    @enum.unique
    class SensorTypes(enum.IntEnum):
        Special = 0
        Silicon_Diode = 1
        GaAlAs_Diode = 2
        Platinium_100_250_ohm = 3
        Platinium_100_500_ohm = 4
        Platinium_1000 = 5
        Rhodium_Iron = 6
        Carbon_Glass = 7
        Cernox = 8
        RuOx = 9
        Germanium = 10
        Capacitor = 11
        Thermocouple = 12

    @enum.unique
    class HeaterRange(enum.IntEnum):
        OFF = 0
        LOW = 1
        MEDIUM = 2
        HIGH = 3
        VERYHIGH = 4
        HIGHEST = 5

    def init_com(self):
        self._model_number = 340
        if "serial" in self.config:
            self._comm = get_comm(self.config, parity="O", bytesize=7, stopbits=1)
        else:
            self._comm = get_comm(self.config)

        self._is_regulation_started = None

    def get_sensor_type(self, tinput):
        """ Read input type parameters

            Args:
                tinput:  Input class type object
                
            Returns:
                dict: {sensor_type: (int), units: (int), coefficient: (int), excitation: (int), range: (int) }

        """
        log_info(self, "get_sensor_type")
        asw = self.send_cmd("INTYPE?", channel=tinput.channel).split(",")
        return {
            "sensor_type": int(asw[0]),
            "units": int(asw[1]),  # 0=special, 1=volts, 2=ohms
            "coefficient": int(asw[2]),  # 0=special, 1=negative, 2=positive
            "excitation": int(asw[3]),
            "range": int(asw[4]),
        }

    def set_sensor_type(
        self,
        tinput,
        sensor_type,
        units=None,
        coefficient=None,
        excitation=None,
        srange=None,
    ):
        """ Set input type parameters

            Args:
                tinput:  Input class type object
                sensor_type   (int): see 'SensorTypes'
                units         (int): specifies input sensor units [ 0=special, 1=volts, 2=ohms ]
                coefficient   (int): specifies input coefficient [ 0=special, 1=negative, 2=positive ]
                excitation    (int): specifies input excitation  [ 0 to 12]
                srange        (int): specifies the input range   [ 1 to 13 ]
            
        """
        log_info(self, "set_sensor_type")
        if (
            units is None
            and coefficient is None
            and excitation is None
            and srange is None
        ):
            self.send_cmd("INTYPE", sensor_type, channel=tinput.channel)
        else:

            if None in [units, coefficient, excitation, srange]:
                asw = self.send_cmd("INTYPE?", channel=tinput.channel).split(",")

                if units is None:
                    units = asw[1]

                if coefficient is None:
                    coefficient = asw[2]

                if excitation is None:
                    excitation = asw[3]

                if srange is None:
                    srange = asw[4]

            self.send_cmd(
                "INTYPE",
                sensor_type,
                units,
                coefficient,
                excitation,
                srange,
                channel=tinput.channel,
            )

    def get_loop_params(self, tloop):
        """ Read Control Loop Parameters
            Args:
                tloop:  Loop class type object
    
            Returns:
                input (str): the associated input channel, see 'VALID_INPUT_CHANNELS'
                unit (str):  the loop setpoint units, could be Kelvin(1), Celsius(2) or Sensor_unit(3)
                onoff (str): control loop status on or off
                powerup (str): powerup mode
        """
        log_info(self, "get_loop_params")
        asw = self.send_cmd("CSET?", channel=tloop.channel).split(",")
        input_chan = asw[0]
        unit = self.REVUNITS[int(asw[1])]
        onoff = "ON" if int(asw[2]) == 1 else "OFF"
        powerup = "ON" if int(asw[3]) == 1 else "OFF"
        return {"input": input_chan, "unit": unit, "onoff": onoff, "powerup": powerup}

    def set_loop_params(self, tloop, input_channel=None, unit=None, onoff=None):
        """ Set Control Loop Parameters
            Args:
                tloop:  Loop class type object
                input_channel (str): the associated input channel, see 'VALID_INPUT_CHANNELS'
                unit (str):  the loop setpoint units, could be Kelvin(1), Celsius(2) or Sensor_unit(3)
                onoff (str): control loop status on or off
        """

        log_info(self, "set_loop_params")
        inputc, unitc, onoffc, powerupc = self.send_cmd(
            "CSET?", channel=tloop.channel
        ).split(",")
        if input_channel is None:
            input_channel = inputc
        if unit is None:
            unit = unitc
        elif unit != "Kelvin" and unit != "Celsius" and unit != "Sensor_unit":
            raise ValueError(
                "Error: acceptables values for unit are 'Kelvin' or 'Celsius' or 'Sensor_unit'."
            )
        else:
            unit = self.UNITS[unit]
        if onoff is None:
            onoff = onoffc
        elif onoff != "on" and onoff != "off":
            raise ValueError("Error: acceptables values for onoff are 'on' or 'off'.")
        else:
            onoff = 1 if onoff == "on" else 0
            if onoff == 1:
                # Get heater range value
                htr_range = int(self.send_cmd("RANGE?"))
                if htr_range == 0:
                    self.send_cmd("RANGE", 1)
        self.send_cmd("CSET", input_channel, unit, onoff, 0, channel=tloop.channel)

    def set_heater_range(self, touput, value):
        """ Set the heater range  (see self.HeaterRange)
            args:
                - touput:  Output class type object 
                - value (int): the value of the range
        """
        log_info(self, "set_heater_range")
        v = self.HeaterRange(value).value
        self.send_cmd("RANGE", v)

    def _set_loop_on(self, tloop):
        log_info(self, "_set_loop_on")
        if self._is_regulation_started in [None, False]:
            self.set_loop_params(tloop, onoff="on")
            self._is_regulation_started = True

        if tloop.output.range == self.HeaterRange.OFF:
            tloop.output.range = self.HeaterRange.LOW.value  # LOW = 1

    def _set_loop_off(self, tloop):
        log_info(self, "_set_loop_off")
        self.set_loop_params(tloop, onoff="off")
        tloop.output.range = self.HeaterRange.OFF.value  # OFF = 0
        self._is_regulation_started = False
