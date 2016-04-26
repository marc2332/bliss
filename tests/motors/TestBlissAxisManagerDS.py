import unittest
import sys
import os
import PyTango

from bliss.config import static


class TestBlissAxisManagerDS(unittest.TestCase):
    def setUp(self):
        try:
            self.blname = os.environ['BEAMLINENAME']
            # print "beamline name=",os.environ['BEAMLINENAME']
        except:
            print "No BEAMLINENAME defined"

        self.dev = PyTango.DeviceProxy("id26/emotion_batest/ba1")

    def test_get(self):
        # print "dev.name=", self.dev.name()
        self.assertEqual(self.dev.name().lower(), "%s/emotion_batest/ba1" % self.blname.lower())

    def test_read_write_velocity(self):
        # Saves velocity.
        _prev_vel = self.dev.velocity

        # Sets velocity to 4.77 and re-read it.
        self.dev.velocity= 4.77
        self.assertEqual(self.dev.velocity, 4.77)

        # Restores velocity.
        self.dev.velocity= _prev_vel

    def test_read_velocity(self):
        a = self.dev.velocity

    def test_custom_commands(self):
        # test no arg in
        self.assertEqual(self.dev.custom_get_forty_two() , 42)
        # test arg / arg out + renaming
        self.assertEqual(self.dev.CustomGetTwice(55) , 110)
        # test strings
        self.assertEqual(self.dev.custom_get_chapi("cahpi") , "bla")

    def test_custom_attribute(self):
        self.assertEqual(self.dev.voltage, 220)
        self.dev.voltage = 380
        self.assertEqual(self.dev.voltage, 380)
        self.dev.voltage = 220
        self.assertEqual(self.dev.voltage, 220)

if __name__ == '__main__':
    unittest.main()

