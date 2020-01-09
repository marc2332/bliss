# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 332, acessible via GPIB and Serial line (RS232)

yml configuration example:
#controller:
- class: LakeShore332
  module: temperature.lakeshore.lakeshore332
  name: lakeshore332
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 12
     eol: "\r\n"     
  # serial:
  #    url: ser2net://lid102:28000/dev/ttyR1
  #    baudrate: 9600    # = max (other possible values: 300, 1200)
  #    eol: "\r\n"     
  inputs:
    - name: ls332_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_332
    - name: ls332_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls332_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls332_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_332
    - name: ls332_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
      type: temperature_C
    - name: ls332_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

  outputs:
    - name: ls332o_1
      channel: 1 
    - name: ls332o_2
      channel: 2 

  ctrl_loops:
    - name: ls332l_1
      input: $ls332_A
      output: $ls332o_1
      channel: 1
    - name: ls332l_2
      input: $ls332_B
      output: $ls332o_2
      channel: 2
"""

import time
import enum
from bliss.comm.util import get_comm

from bliss.controllers.regulation.temperature.lakeshore.lakeshore331 import LakeShore331
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
# lakeshore 332 supports at most 20 commands per second
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


class LakeShore332(LakeShore331):
    @enum.unique
    class SensorTypes(enum.IntEnum):
        Silicon_Diode = 0
        GaAlAs_Diode = 1
        Platinium_250_100_ohm = 2
        Platinium_500_100_ohm = 3
        Platinium_1000_ohm = 4
        NTC_RTD_75_mV_7500_ohm = 5
        Thermocouple_25_mV = 6
        Thermocouple_50_mV = 7
        NTC_RTD_75_mV_75_ohm = 8
        NTC_RTD_75_mV_750_ohm = 9
        NTC_RTD_75_mV_7500_ohm_bis = 10
        NTC_RTD_75_mV_75000_ohm = 11
        NTC_RTD_75_mV_auto = 12

    def init_com(self):
        self._model_number = 332
        if "serial" in self.config:
            self._comm = get_comm(self.config, parity="O", bytesize=7, stopbits=1)
        else:
            self._comm = get_comm(self.config)
