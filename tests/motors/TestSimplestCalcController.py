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
  <controller class="mockup">
    <axis name="m0">
      <backlash value="0.1" />
      <velocity value="100" />
      <acceleration value="1" />
    </axis>
  </controller>
  <controller class="simpliest">
    <axis name="m0" tags="real m0" />
    <axis name="m1" tags="m1" />
  </controller>
</config>
"""


class TestSimplest(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def testMoveReal(self):
        m1 = bliss.get_axis("m1")
        m0 = bliss.get_axis("m0")
        p1 = m1.position()
        p0 = m0.position()
        m0.rmove(1)
        self.assertEquals(p0 + 1, m0.position())
        self.assertEquals(m1.position(), p1 + 2)
        m0.rmove(-1)
        self.assertEquals(p0, m0.position())
        self.assertEquals(m1.position(), p1)

    def testMovePseudo(self):
        m1 = bliss.get_axis("m1")
        m0 = bliss.get_axis("m0")
        p1 = m1.position()
        p0 = m0.position()
        m1.rmove(2)
        self.assertEquals(p1 + 2, m1.position())
        self.assertEquals(m0.position(), p0 + 1)
        m1.rmove(-2)
        self.assertEquals(p0, m0.position())
        self.assertEquals(m1.position(), p1)

if __name__ == '__main__':
    unittest.main()
