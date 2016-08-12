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
from bliss.common.axis import Axis

import bliss
import bliss.controllers.motor_settings
from bliss.common.axis import Axis
from bliss.common import event
from bliss.common import log
from bliss.config.motors import set_backend
from bliss.config import settings


class TestEncoder(unittest.TestCase):

    def setUp(self):
        set_backend("beacon")
        bliss.config.motors.clear_cfg()
        bliss.controllers.motor_settings.wait_settings_writing()

    def test_get_axis(self):
        ba1 = bliss.get_axis("ba1")
        self.assertTrue(ba1)

    def test_custom_attribute_read(self):
        ba1 = bliss.get_axis("ba1")
        ba2 = bliss.get_axis("ba2")
        self.assertEqual(ba1.custom_get_forty_two(), 42)

        self.assertAlmostEquals(ba1.get_cust_attr_float(), 3.14, places=3)
        self.assertAlmostEquals(ba2.get_cust_attr_float(), 6.28, places=3)

    def test_custom_attribute_rw(self):
        ba1 = bliss.get_axis("ba1")

        self.assertEqual(ba1.get_voltage(), 110)
        ba1.set_voltage(380)
        self.assertEqual(ba1.get_voltage(), 380)
        ba1.set_voltage(110)
        self.assertEqual(ba1.get_voltage(), 110)


    def test_custom_park(self):
        ba1 = bliss.get_axis("ba1")
        ba1.custom_park()

    def test_custom_get_forty_two(self):
        ba1 = bliss.get_axis("ba1")
        self.assertEqual(ba1.custom_get_forty_two(), 42)

    def test_custom_get_twice(self):
        ba1 = bliss.get_axis("ba1")
        self.assertEqual(ba1.CustomGetTwice(42), 84)

    def test_custom_get_chapi(self):
        ba1 = bliss.get_axis("ba1")
        self.assertEqual(ba1.custom_get_chapi("chapi"), "chapo")
        self.assertEqual(ba1.custom_get_chapi("titi"), "toto")
        self.assertEqual(ba1.custom_get_chapi("roooh"), "bla")

    def test_custom_send_command(self):
        ba1 = bliss.get_axis("ba1")
        ba1.custom_send_command("SALUT sent")

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEncoder)
    unittest.TextTestRunner(verbosity=1).run(suite)
