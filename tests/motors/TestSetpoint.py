# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import gevent
import time
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss
from bliss.common.axis import Axis

config_xml = """
<config>
  <controller class="setpoint" name="test">
    <target_attribute value="ID26/emotion_batest/ba1/voltage"/>
    <port value="5000"/>
    <gating_ds value="ID26/emotion_batest/ba2"/>
    <axis name="sp1">
      <!-- degrees per second -->
      <velocity value="100"/>
    </axis>
  </controller>
</config>
"""

class TestSetpointController(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        sp1 = bliss.get_axis("sp1")
        self.assertTrue(sp1)

if __name__ == '__main__':
    unittest.main()
