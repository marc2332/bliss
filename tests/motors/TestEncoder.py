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


#from bliss.common import log
#log.level(log.DEBUG)

config_xml = """
<config>
  <controller class="mockup">
    <encoder name="m0enc">
      <steps_per_unit value="50"/>
      <tolerance value="0.001"/>
    </encoder>
    <encoder name="tiltenc">
      <steps_per_unit value="50"/>
    </encoder>
    <axis name="m0">
      <velocity value="50"/>
      <acceleration value="1"/>
      <encoder value="m0enc"/>
      <steps_per_unit value="1000"/>
    </axis>
    <axis name="m1">
      <velocity value="50"/>
      <acceleration value="1"/>
      <steps_per_unit value="1000"/>
    </axis>
  </controller>
  <!--<controller class="tab2">
    <axis name="s1f" tags="real front"/>
    <axis name="s1b" tags="real back"/>
    <axis name="s1vg" tags="vgap" encoder="tiltenc"/>
  </controller>
  -->
</config>
"""


class TestEncoder(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)
    
    def test_get_encoder(self):
        enc = bliss.get_encoder("m0enc")
        self.assertTrue(enc)
        self.assertEquals(enc.steps_per_unit, 50)
        m0 = bliss.get_axis("m0")
        self.assertEquals(m0.encoder, enc)
        m1 = bliss.get_axis("m1")
        self.assertEquals(m1.encoder, None)

    def test_encoder_read(self):
        m0 = bliss.get_axis("m0")
        _pos = m0.dial()
        enc = bliss.get_encoder("m0enc")
        self.assertEquals(enc.read(), m0.dial()/enc.steps_per_unit)

    def test_encoder_set(self):
        m0 = bliss.get_axis("m0")
        _pos = m0.dial()
        enc = bliss.get_encoder("m0enc")
        self.assertEquals(enc.set(133), 133)

    def test_axis_get_noisy_measured_position(self):
        m0 = bliss.get_axis("m0")
        _pos = m0.dial()
        # Switch to noisy mode.
        m0.custom_set_measured_noise(0.1)
        self.failIf( abs(_pos - m0.dial_measured_position()) > 0.1)
        # switch back to normal mode.
        m0.custom_set_measured_noise(0.0)

    def test_tolerance(self):
        enc = bliss.get_encoder("m0enc")
        self.assertEquals(enc.tolerance, 0.001)
    
    def test_maxee(self):
        m1 = bliss.get_axis("m1")
        m1.move(1)
        self.assertEquals(m1.position(), 1)

        enc = bliss.get_encoder("m0enc")
        enc.read() #make sure encoder is initialized
        m0 = bliss.get_axis("m0")
        m0.dial(0); m0.position(0)
        m0.custom_set_measured_noise(0.1)
        self.assertRaises(RuntimeError, m0.move, 5)
        m0.custom_set_measured_noise(0)

        enc.set(2)
        m0.move(2)
        self.assertEquals(m0.position(), 2)
    
    def test_encoder_move(self):
        m0 = bliss.get_axis("m0")
        m0.move(5)
        self.assertAlmostEquals(m0.position(), m0.encoder.read(), places=4)

    def test_encoder_axis_init(self):
        # Initialisation problem...
        # ok with _pos = m0.dial()
        m0 = bliss.get_axis("m0")
        # _pos = m0.dial()
        enc = bliss.get_encoder("m0enc")
        self.assertEquals(enc.set(133), 133)
    
if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEncoder)
    unittest.TextTestRunner(verbosity=1).run(suite)

