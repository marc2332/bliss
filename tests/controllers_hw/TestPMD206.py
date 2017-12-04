# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os
import time

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss

config_xml = """
<config>
  <controller class="PMD206" name="id16pmd206">
    <host value="pmd206id16ni2"/>
    <axis name="pm1">
      <channel            value="1"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm2">
      <channel       value="2"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm3">
      <channel            value="3"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm4">
      <channel            value="4"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm5">
      <channel            value="5"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm6">
      <channel            value="6"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
  </controller>
</config>
"""


class TestPMD206Controller(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_chan(self):
        pm1 = bliss.get_axis("pm1")
        print "PMD206 channel :", pm1.channel

    def test_get_info(self):
        pm1 = bliss.get_axis("pm1")
        print "PMD206 info :"
        print pm1.get_info()

    # called at end of each test
    def tearDown(self):
        # Little wait time to let time to PMD206 controller to
        # close peacefully its sockets... (useful ?)
        time.sleep(0.2)


if __name__ == '__main__':
    unittest.main()


'''
# interactive test:



load_cfg_fromstring("""
<config>
  <controller class="PMD206" name="id16pmd206">
    <host value="pmd206id16ni2"/>
    <axis name="pm1">
      <channel            value="1"/>
      <steps_per_unit     value="200"/>
    </axis>
    <axis name="pm2">
      <channel            value="2"/>
      <steps_per_unit     value="200"/>
    </axis>
    <axis name="pm3">
      <channel            value="3"/>
      <steps_per_unit     value="200"/>
    </axis>
    <axis name="pm4">
      <channel            value="4"/>
      <steps_per_unit     value="200"/>
    </axis>
    <axis name="pm5">
      <channel            value="5"/>
      <steps_per_unit     value="200"/>
    </axis>
    <axis name="pm6">
      <channel            value="6"/>
      <steps_per_unit     value="200"/>
    </axis>
  </controller>
</config>
""") ; p = get_axis("pm6")

p.controller.pmd206_get_status(p)

print p.controller.get_controller_status()
print p.controller.get_motor_status(p)

# text status
print p.controller.status(p)

print p.measured_position()
print p.state()


# conversion from hex to decimal:
print int(p.controller.send(p, "MP?")[8:], 16)

print p.controller.send(p, "CS?")
# PM16CS?:0100,20,20,20,20,20,20

'''
