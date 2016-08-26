# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="1"/>
      <default_voltage value="110"/>
      <default_cust_attr value="3.14"/>
    </axis>
    <axis name="roby">
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="1"/>
      <default_voltage value="220"/>
      <default_cust_attr value="6.28"/>
    </axis>

  </controller>
</config>
"""

class TestCustomAttributes(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        robz = bliss.get_axis("robz")
        self.assertTrue(robz)


    def test_custom_attribute_read(self):
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("robz")

        self.assertAlmostEquals(roby.get_cust_attr_float(), 6.28, places=3)

        self.assertAlmostEquals(robz.get_cust_attr_float(), 3.14, places=3)

    def test_custom_attribute_rw(self):
        robz = bliss.get_axis("robz")

        self.assertEqual(robz.get_voltage(), 110)
        robz.set_voltage(380)
        self.assertEqual(robz.get_voltage(), 380)
        robz.set_voltage(110)
        self.assertEqual(robz.get_voltage(), 110)


if __name__ == '__main__':
    unittest.main()
