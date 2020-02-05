# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os
import PyTango

from bliss.config import static


class TestBlissAxisManagerDS(unittest.TestCase):
    def setUp(self):
        try:
            self.blname = os.environ["BEAMLINENAME"]
            # print "beamline name=",os.environ['BEAMLINENAME']
        except:
            print("No BEAMLINENAME defined")

        self.ba1 = PyTango.DeviceProxy("id26/emotion_batest/ba1")
        self.ba2 = PyTango.DeviceProxy("id26/emotion_batest/ba2")

        self.ba1.ApplyConfig(True)
        self.ba2.ApplyConfig(True)

    def test_get(self):
        # print "ba1.name=", self.ba1.name()
        self.assertEqual(
            self.ba1.name().lower(), "%s/emotion_batest/ba1" % self.blname.lower()
        )

    def test_read_write_velocity(self):
        # Saves velocity.
        _prev_vel = self.ba1.velocity

        # Reads velocities of 2 different axis.
        self.assertAlmostEqual(self.ba1.velocity, 3.888, places=5)
        self.assertAlmostEqual(self.ba2.velocity, 2.444, places=5)

        # Sets velocity to 4.777 and re-read it.
        self.ba1.velocity = 4.777
        self.assertEqual(self.ba1.velocity, 4.777)

        # Restores velocity.
        self.ba1.velocity = _prev_vel

    def test_read_velocity(self):
        a = self.ba1.velocity

    def test_custom_commands(self):
        # test no arg in
        self.assertEqual(self.ba1.custom_get_forty_two(), 42)
        # test arg / arg out + renaming
        self.assertEqual(self.ba1.CustomGetTwice(55), 110)
        # test strings
        self.assertEqual(self.ba1.custom_get_chapi("cahpi"), "bla")

    def test_custom_attribute(self):

        try:
            # ints
            self.assertEqual(self.ba1.voltage, 110)
            self.assertEqual(self.ba2.voltage, 220)
            # floats
            self.assertAlmostEqual(self.ba1.cust_attr_float, 3.14, places=3)
            self.assertAlmostEqual(self.ba2.cust_attr_float, 6.28, places=5)

            self.ba1.voltage = 381
            self.ba2.voltage = 10101
            self.assertEqual(self.ba1.voltage, 381)
            self.assertEqual(self.ba2.voltage, 10101)

            self.ba1.cust_attr_float = 1.4142
            self.ba2.cust_attr_float = 2.8284

            self.assertAlmostEqual(self.ba1.cust_attr_float, 1.4142, places=5)
            self.assertAlmostEqual(self.ba2.cust_attr_float, 2.8284, places=5)

        finally:
            # Re-set values to original ones
            self.ba1.voltage = 110
            self.ba2.voltage = 220
            # floats
            self.ba1.cust_attr_float = 3.14
            self.ba2.cust_attr_float = 6.28


if __name__ == "__main__":
    unittest.main()
