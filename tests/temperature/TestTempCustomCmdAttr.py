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
import time

SP = 10
SP = 15
SP = 20

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
from bliss.common import log;
from bliss.config import static

"""
UnitTest list of tests
"""


class TestMockupTempController(unittest.TestCase):

    # called for each test
    def setUp(self):
        pass

    # called at the end of each individual test
    def tearDown(self):
        pass

    def test_creation_input(self):
        config = static.get_config()
        aa=config.get("thermo_sample")
        self.assertTrue(aa)

    def test_creation_output(self):
        config = static.get_config()
        bb=config.get("heater")
        self.assertTrue(bb)

    def test_custom_attr(self):
        config = static.get_config()
        bb=config.get("heater")
        self.assertEqual(bb.get_material(), "Hg")
        bb.set_material("CH4OH")
        self.assertEqual(bb.get_material(), "CH4OH")

    def test_custom_cmd(self):
        config = static.get_config()
        aa=config.get("thermo_sample")
        self.assertEqual(aa.get_double_str("calor"), "calor_calor")


"""
Main entry point
"""
if __name__ == '__main__':


    # Launch the tests sequence
    print "\nTesting Mockup Temperature controller\n"
    print "\n".rjust(70, "-")

    # Change the default unittest test sequence order from cmp() to line number
    loader = unittest.TestLoader()
    ln = lambda f: getattr(TestMockupTempController, f).\
        im_func.func_code.co_firstlineno
    lncmp = lambda a, b: cmp(ln(a), ln(b))
    loader.sortTestMethodsUsing = lncmp

    # NOTE: unittest.main(verbosity=2) not supported under Python 2.6
    suite  = loader.loadTestsFromTestCase(TestMockupTempController)
    unittest.TextTestRunner(verbosity=3).run(suite)

    # normal end
