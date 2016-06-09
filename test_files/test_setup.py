# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import emotion
from bliss.common import Actuator, Shutter
from bliss.common.essentials import *
from bliss.common.measurement import CounterBase
from random import randint
import time

config_xml = """
<config>
  <controller class="mockup">
    <axis name="m0">
      <steps_per_unit value="10000"/>
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="3"/>
      <low_limit value="-1000"/>
      <high_limit value="1E9"/>
    </axis>
    <axis name="m1">
      <steps_per_unit value="10000"/>
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="3"/>
      <low_limit value="-1000"/>
      <high_limit value="1E9"/>
    </axis>
    <axis name="m2">
      <steps_per_unit value="10000"/>
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="3"/>
      <low_limit value="-1000"/>
      <high_limit value="1E9"/>
    </axis>
  </controller>
</config>
"""

emotion.load_cfg_fromstring(config_xml)

m0 = emotion.get_axis("m0")
m1 = emotion.get_axis("m1")
m2 = emotion.get_axis("m2")

class dummy_diode(CounterBase):
    def __init__(self, name, gain_factors=None):
        CounterBase.__init__(self, name)
        self.gain_factors = gain_factors

    def read(self, count_time=0):
        time.sleep(count_time)
        raw_value = randint(0,9999)
        if self.gain_factors != None:
            gain = self.gain_factors[randint(0,len(self.gain_factors)-1)]
        else:
            gain = 1
        return raw_value/gain

    def set(self, value):
        return value

i0 = dummy_diode("i0")

light = Actuator(lambda: True, lambda: True)

safshut = Shutter(lambda: True, lambda: True)

print 'HELLO'
