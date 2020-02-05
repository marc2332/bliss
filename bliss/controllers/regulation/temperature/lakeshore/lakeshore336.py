# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Lakeshore 336, acessible via GPIB, USB or Ethernet

yml configuration example:
#controller:
- class: LakeShore336
  module: temperature.lakeshore.lakeshore336
  name: lakeshore336
  timeout: 3
  gpib:
     url: enet://gpibid10f.esrf.fr
     pad: 9
     eol: '\r\n' 
  usb:
     url: ser2net://lid102:28000/dev/ttyUSB0
     baudrate: 57600    # = the only possible value
#ethernet
  tcp:
     #url: idxxlakeshore:7777
     url: lakeshore336se2:7777
  inputs:
    - name: ls336_A
      channel: A 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_336
    - name: ls336_A_c    # input temperature in Celsius
      channel: A
      unit: Celsius
    - name: ls336_A_su  # in sensor units (Ohm or Volt)
      channel: A
      unit: Sensor_unit

    - name: ls336_B
      channel: B 
      # possible set-point units: Kelvin, Celsius, Sensor_unit
      unit: Kelvin
      #tango_server: ls_336
    - name: ls336_B_c    # input temperature in Celsius
      channel: B
      unit: Celsius
    - name: ls336_B_su  # in sensor units (Ohm or Volt)
      channel: B
      unit: Sensor_unit

    # can add also input channels C and D

  outputs:
    - name: ls336o_1
      channel: 1 
      unit: Kelvin
    - name: ls336o_2
      channel: 2 

  ctrl_loops:
    - name: ls336l_1
      input: $ls336_A
      output: $ls336o_1
      channel: 1
    - name: ls336l_2
      input: $ls336_B
      output: $ls336o_2
      channel: 2

    # can add also output channels 3 and 4

"""

import time
from bliss.comm.util import get_comm
from bliss.common.logtools import log_info

from bliss.controllers.regulation.temperature.lakeshore.lakeshore335 import (
    LakeShore335,
    Input,
)


from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreOutput as Output
)
from bliss.controllers.regulation.temperature.lakeshore.lakeshore import (
    LakeshoreLoop as Loop
)


_last_call = time.time()
# limit number of commands per second
# lakeshore 336 supports at most 20 commands per second
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


class LakeShore336(LakeShore335):

    NUMINPUT = {1: "A", 2: "B", 3: "C", 4: "D"}
    REVINPUT = {"A": 1, "B": 2, "C": 3, "D": 4}

    VALID_INPUT_CHANNELS = ["A", "B", "C", "D"]
    VALID_OUTPUT_CHANNELS = [1, 2]  # [1, 2, 3, 4]
    VALID_LOOP_CHANNELS = [1, 2]

    def init_com(self):
        self._model_number = 336
        if "serial" in self.config:
            self._comm = get_comm(
                self.config, baudrate=57600, parity="O", bytesize=7, stopbits=1
            )
        else:
            self._comm = get_comm(self.config)

    @property
    def eol(self):
        eol = self._comm._eol
        if isinstance(eol, bytes):
            return eol.decode()
        return eol

    def read_value_percent(self, touput):
        """ return ouptut current value as a percentage (%)
            args:
                touput:  Output class type object 
        """
        log_info(self, "read_value_percent")
        if int(touput.channel) in [1, 2]:
            return self.send_cmd("HTR?", channel=touput.channel)
        elif int(touput.channel) in [3, 4]:
            return self.send_cmd("AOUT?", channel=touput.channel)
        else:
            raise ValueError(
                f"Wrong output channel: '{touput.channel}' should be in {self.VALID_OUTPUT_CHANNELS} "
            )
