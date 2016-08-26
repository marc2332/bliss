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
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby">
      <backlash value="2"/>
      <steps_per_unit value="10"/>
      <velocity  value="2500"/>
      <acceleration value="1"/>
    </axis>
  </controller>
</config>
"""

class TestMockupController(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        robz = bliss.get_axis("robz")
        self.assertTrue(robz)

    def test_get_custom_methods_list(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.custom_methods_list, [('Set_Closed_Loop', ('bool', 'None')), ('custom_command_no_types', (None, None)), ('custom_get_chapi', ('str', 'str')), ('custom_get_forty_two', ('None', 'int')), ('CustomGetTwice', ('int', 'int')), ('custom_park', (None, None)), ('custom_send_command', ('str', 'None')), ('custom_set_measured_noise', ('float', 'None')), ('get_cust_attr_float', ('None', 'float')), ('get_voltage', ('None', 'int')), ('set_cust_attr_float', ('float', 'None')), ('set_voltage', ('int', 'None'))])

        #print "\ncustom functions :",
        #for (fname, types) in robz.custom_methods_list:
        #    print fname, types, "         ",

    def test_custom_park(self):
        robz = bliss.get_axis("robz")
        robz.custom_park()

    def test_custom_get_forty_two(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.custom_get_forty_two(), 42)

    def test_custom_get_twice(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.CustomGetTwice(42), 84)

    def test_custom_get_chapi(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.custom_get_chapi("chapi"), "chapo")
        self.assertEqual(robz.custom_get_chapi("titi"), "toto")
        self.assertEqual(robz.custom_get_chapi("roooh"), "bla")

    def test_custom_send_command(self):
        robz = bliss.get_axis("robz")
        robz.custom_send_command("SALUT sent")


if __name__ == '__main__':
    unittest.main()

