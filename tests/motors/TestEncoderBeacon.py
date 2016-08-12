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

    def test_encoder_beacon_move(self):
        # Does not pass with pre-lazy-init versions.
        ba2 = bliss.get_axis("ba2")
        enc2 = bliss.get_encoder("enc2")
        ba2.move(1)
        self.assertAlmostEquals(enc2.read(), ba2.position(), places=5)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEncoder)
    unittest.TextTestRunner(verbosity=2).run(suite)
