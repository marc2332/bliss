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
from bliss.common.axis import READY,MOVING

config_xml = """
<config>
  <controller class="NF8753">
    <host value="newfocusid30a3"/>
    <axis name="a1">
      <driver value="A1"/>
      <channel value="0"/>
      <steps_per_unit value="50"/>
      <velocity value="10" />
    </axis>
    <axis name="a2">
      <driver value="A1"/>
      <channel value="1"/>
      <steps_per_unit value="50"/>
      <velocity value="10" />
      <settings><low_limit value="-1000000000.0" /><high_limit value="1000000000.0" /><velocity value="10.0" /><offset value="0.2"/></settings>
    </axis>
  </controller>
</config>
"""


class TestNewFocus(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)
    
    def testVelocity(self):
        a1 = bliss.get_axis("a1")
        self.assertEquals(a1.velocity(1), 1)
        config_velocity = a1.config.get("velocity", int)
        self.assertEquals(a1.velocity(config_velocity), config_velocity)
        a2 = bliss.get_axis("a2")
        config_velocity = a2.config.get("velocity", int)
        self.assertEquals(a2.velocity(config_velocity), config_velocity)
    
    def testPosition(self):
          a1 = bliss.get_axis("a1")
          a2 = bliss.get_axis("a2")
          self.assertAlmostEqual(a2.position(), 0.2, places=5)
          
          for a in (a1, a2):
            p0 = a.position()
            target = p0+0.1
            a.move(target)
            self.assertAlmostEqual(a.position(), target, places=5)
            a.move(p0-0.1)
            self.assertAlmostEqual(a.position(), p0-0.1, places=5)  

    def testState(self):
        a1 = bliss.get_axis("a1")
        self.assertEquals(a1.state(), READY)
    
    def testSimultaneousMove(self):
        a1 = bliss.get_axis("a1")
        a2 = bliss.get_axis("a2")
        p1 = a1.position()
        p2 = a2.position()
        a1.rmove(0.1, wait=False)
        self.assertRaises(RuntimeError, a2.rmove, 0.1, wait=False)
        a1.wait_move()
        a2.wait_move()
        self.assertEquals(a1.position(), p1+0.1)
        self.assertEquals(a2.position(), p2) 
        a1.rmove(-0.1)
        self.assertEquals(a1.position(), p1)

if __name__ == '__main__':
    unittest.main()
