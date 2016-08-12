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
from bliss.tango.servers import TgGevent

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <velocity value="100"/>
      <acceleration value="1"/>
    </axis>
  </controller>
</config>
"""


class TestThread(unittest.TestCase):

    def setUp(self):
        TgGevent.execute(bliss.load_cfg_fromstring, config_xml)

    def test_get_axis(self):
        robz = TgGevent.get_proxy(bliss.get_axis, "robz")
        self.assertTrue(robz)

    def test_axis_move(self):
        robz = TgGevent.get_proxy(bliss.get_axis, "robz")
        self.assertEqual(robz.state(), "READY")
        robz.move(180, wait=False)
        self.assertEqual(robz.state(), "MOVING")
        robz.wait_move()
        self.assertEqual(robz.state(), "READY")

    def test_stop(self):
        robz = TgGevent.get_proxy(bliss.get_axis, "robz")
        self.assertEqual(robz.state(), "READY")
        robz.move(180, wait=False)
        self.assertEqual(robz.state(), "MOVING")
        robz.stop()
        self.assertEqual(robz.state(), "READY")

    @classmethod
    def tearDownClass(cls):
        TgGevent.execute("exit")

if __name__ == '__main__':
    unittest.main()
