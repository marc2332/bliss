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
import bliss.config.motors
from bliss.common.axis import Axis, READY
from bliss.common import log
from bliss.config import settings

#log.level(log.DEBUG)

class TestBeaconSlits(unittest.TestCase):

    def setUp(self):
        bliss.config.motors.set_backend("beacon")
        bliss.config.motors.clear_cfg()
        bliss.controllers.motor_settings.wait_settings_writing()
        for axis_name in ('s1f','s1b','s1u','s1d','s1hg','s1vg','s1ho','s1vo'):
            settings.HashSetting("axis.%s" % axis_name).clear()
        
    def testTags(self):
        s1ho = bliss.get_axis("s1ho")
        controller = s1ho.controller
        for tag, axis_name in {"front": "s1f",
                               "back": "s1b",
                               "up": "s1u",
                               "down": "s1d",
                               "hgap": "s1hg",
                               "hoffset": "s1ho",
                               "vgap": "s1vg",
                               "voffset": "s1vo"}.iteritems():
            self.assertEquals(controller._tagged[tag][0].name, axis_name)

    def testRealTags(self):
        s1ho = bliss.get_axis("s1ho")
        controller = s1ho.controller
        self.assertEquals(
            [x.name for x in controller._tagged["real"]],
            ["s1f", "s1b", "s1u", "s1d"])

    def testHasTag(self):
        self.assertTrue(bliss.get_axis("s1ho").has_tag("hoffset"))
        self.assertFalse(bliss.get_axis("s1ho").has_tag("vgap"))
        self.assertFalse(bliss.get_axis("s1vg").has_tag("real"))
        self.assertTrue(bliss.get_axis("s1u").has_tag("real"))

    def testRealsList(self):
        s1ho = bliss.get_axis("s1ho")
        controller = s1ho.controller
        self.assertEquals(len(controller.reals), 4)
        self.assertTrue(all([isinstance(x, Axis) for x in controller.reals]))

    def testPseudosList(self):
        s1ho = bliss.get_axis("s1ho")
        controller = s1ho.controller
        self.assertEquals(len(controller.pseudos), 4)
        self.assertTrue(all([isinstance(x, Axis) for x in controller.pseudos]))

    def testPseudoAxisAreExported(self):
        self.assertTrue(all((bliss.get_axis("s1vg"),
                             bliss.get_axis("s1vo"),
                             bliss.get_axis("s1hg"),
                             bliss.get_axis("s1ho"))))

    def testRealAxisIsRightObject(self):
        s1f = bliss.get_axis('s1f')
        m0 = bliss.get_axis('m0')
        s1ho = bliss.get_axis("s1ho")
        controller = s1ho.controller
        self.assertEquals(s1f.controller, m0.controller)
        self.assertEquals(s1f, controller.axes['s1f'])

    def testPseudoAxisState(self):
        self.testPseudoAxisAreExported()
        s1ho = bliss.get_axis("s1ho")
        controller = s1ho.controller
        self.assertTrue(
            all([axis.state() == 'READY' for axis in controller.pseudos]))

    def testPseudoAxisPosition(self):
        self.testPseudoAxisAreExported()
        s1f = bliss.get_axis("s1f")
        s1b = bliss.get_axis("s1b")
        s1u = bliss.get_axis("s1u")
        s1d = bliss.get_axis("s1d")
        s1f.position(0)
        s1b.position(1)
        s1u.position(0)
        s1d.position(1)
        self.assertEquals(bliss.get_axis("s1vg").position(), 1)
        self.assertEquals(bliss.get_axis("s1vo").position(), -0.5)
        self.assertEquals(bliss.get_axis("s1hg").position(), 1)
        self.assertEquals(bliss.get_axis("s1ho").position(), 0.5)

    def testPseudoAxisMove(self):
        s1b  = bliss.get_axis("s1b")
        s1f  = bliss.get_axis("s1f")
        s1hg = bliss.get_axis("s1hg")

        s1f.move(0)
        s1b.move(0)

        hgap = 0.5
        s1hg.move(hgap)
        self.assertAlmostEquals(hgap, s1hg.position(), places=6)

    def testPseudoAxisMove2(self):
        s1ho = bliss.get_axis("s1ho")
        s1b  = bliss.get_axis("s1b")
        s1f  = bliss.get_axis("s1f")
        s1hg = bliss.get_axis("s1hg")

        s1f.move(0)
        s1b.move(0)
        s1hg.move(.5)
        hgap = s1hg.position()
        s1ho.move(2)
        self.assertEquals(s1b.state(), READY)
        self.assertEquals(s1f.state(), READY)
        self.assertAlmostEquals(hgap, s1hg.position(), places=4)
        self.assertEquals(s1b.position(), 2 + (hgap / 2.0))
        self.assertEquals(s1f.position(), (hgap / 2.0) - 2)

    def testPseudoAxisScan(self):
        s1ho = bliss.get_axis("s1ho")
        s1b  = bliss.get_axis("s1b")
        s1f  = bliss.get_axis("s1f")
        s1hg = bliss.get_axis("s1hg")

        s1f.move(0)
        s1b.move(0)

        hgap = 0.5
        s1hg.move(hgap)

        # scan the slits under the motors resolution
        ho_step = (1.0/s1b.steps_per_unit) / 10.0
        for i in range(100):
            s1ho.rmove(ho_step)

        self.assertAlmostEquals(hgap, s1hg.position(), places=4)
     
    def testSetPosition(self):
        s1ho = bliss.get_axis("s1ho")
        s1b  = bliss.get_axis("s1b")
        s1f  = bliss.get_axis("s1f")
        s1hg = bliss.get_axis("s1hg")
        s1b.move(0); s1f.move(0);     
        s1hg.move(4)
        self.assertAlmostEquals(2, s1b.position(), places=4)
        self.assertAlmostEquals(2, s1f.position(), places=4)
        self.assertAlmostEquals(0, s1ho.position(), places=4)
        s1hg.position(0)
        s1hg.move(1)
        self.assertAlmostEquals(2.5, s1b.position(), places=4)
        self.assertAlmostEquals(2.5, s1f.position(), places=4)
        self.assertAlmostEquals(1, s1hg.position(), places=4)
        self.assertAlmostEquals(0, s1ho.position(), places=4)




if __name__ == '__main__':
    unittest.main()
