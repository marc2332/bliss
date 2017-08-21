# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os
import optparse
import re
import signal
import gevent
import pdb


"""
Bliss generic library
"""
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss
from bliss.common import log


"""
Example of Bliss configuration
"""
config_xml_IcePAP = """
<config>
    <controller class="IcePAP" name="test">

        <host value="iceeu2"/>
        <libdebug value="1"/>

        <axis name="mot0">
            <address        value="2"/>
            <steps_per_unit value="2000"/>
            <backlash       value="0.01"/>
            <velocity       value="2500"/>   // unit is mm/sec
            <acceleration   value="10"/>   // unit is mm/sec
        </axis>

        <axis name="mymot2">
            <address        value="3"/>
            <steps_per_unit value="2000"/>
            <backlash       value="0.01"/>
            <velocity       value="2500"/>   // unit is mm/sec
            <acceleration   value="10"/>   // unit is mm/sec
        </axis>

        <encoder name="myenc">
            <address        value="2"/>
            <type           value="encin"/>  // optional
            <steps_per_unit value="1000"/>
        </encoder>

    </controller>
</config>
"""
config_xml = """
<config>
  <controller class="TacoMaxe" name="PEL_tacomot">
    <tacodevice value="//lpellab/PEL/MaxeVpap/marie" />
    <axis name="mot0">
      <channel value="1" />
      <velocity value="2000" />
      <steps_per_unit value="1" />
      <backlash value="0"/>
      <acceleration value="10" />
     </axis>
    <axis name="mot1">
      <channel value="2" />
      <velocity value="3000" />
      <steps_per_unit value="1" />
      <backlash value="0"/>
      <acceleration value="10" />
    </axis>
  </controller>
</config>
"""




"""
UnitTest list of tests
"""


class TestTacoMaxeController(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)
        #bliss.load_cfg_fromstring(config_xml_IcePAP)

    # called at the end of each individual test
    def tearDown(self):
        pass

    def test_axis_creation(self):
        mymot = bliss.get_axis("mot0")
        self.assertTrue(mymot)

    def test_axes_creation(self):
        #log.level(log.INFO)
        mymot  = bliss.get_axis("mot0")
        #log.level(log.ERROR)
        self.assertTrue(mymot)
        mymot2 = bliss.get_axis("mot1")
        self.assertTrue(mymot2)

    def test_set_velocity(self):
        mymot = bliss.get_axis("mot0")
        newvel = 2500
        mymot.velocity(newvel)
        self.assertEqual(mymot.velocity(), newvel)

"""
Main entry point
"""
if __name__ == '__main__':


    # Launch the tests sequence
    print "\nTesting TacoMaxe controller\n"
    print "\n".rjust(70, "-")

    # Change the default unittest test sequence order from cmp() to line number
    loader = unittest.TestLoader()
    ln = lambda f: getattr(TestTacoMaxeController, f).\
        im_func.func_code.co_firstlineno
    lncmp = lambda a, b: cmp(ln(a), ln(b))
    loader.sortTestMethodsUsing = lncmp

    # NOTE: unittest.main(verbosity=2) not supported under Python 2.6
    suite  = loader.loadTestsFromTestCase(TestTacoMaxeController)
    unittest.TextTestRunner(verbosity=3).run(suite)

    # normal end
