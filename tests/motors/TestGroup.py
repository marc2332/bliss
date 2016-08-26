# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
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
from bliss.common import event

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="10"/>
    </axis>
    <axis name="robz2">
      <velocity value="100"/>
      <acceleration value="10"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby">
      <backlash value="2"/>
      <steps_per_unit value="10"/>
      <velocity  value="200"/>
      <acceleration value="10"/>
    </axis>
  </controller>
</config>
"""


class TestGroup(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)
        self.grp = bliss.Group(bliss.get_axis("robz"),
                                  bliss.get_axis("robz2"),
                                  bliss.get_axis("roby"))
   
    def test_group_creation(self):
        self.assertTrue(self.grp)
    
    def test_group_move(self):
        robz = bliss.get_axis("robz")
        robz_pos = robz.position()
        roby = bliss.get_axis("roby")
        roby_pos = roby.position()

        self.assertEqual(self.grp.state(), "READY")

        target_robz = robz_pos + 50
        target_roby = roby_pos + 50

        self.grp.move(
            robz, target_robz,
            roby, target_roby,
            wait=False)

        self.assertEqual(self.grp.state(), "MOVING")
        self.assertEqual(robz.state(), "MOVING")
        self.assertEqual(roby.state(), "MOVING")

        self.grp.wait_move()

        self.assertEqual(robz.state(), "READY")
        self.assertEqual(roby.state(), "READY")
        self.assertEqual(self.grp.state(), "READY")
    
    def test_stop(self):
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        self.grp.move({robz: 0, roby: 0}, wait=False)
        self.assertEqual(self.grp.state(), "MOVING")
        self.grp.stop()
        self.assertEqual(self.grp.state(), "READY")
        self.assertEqual(robz.state(), "READY")
        self.assertEqual(roby.state(), "READY")
     
    def test_ctrlc(self):
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        self.grp.rmove({robz: -10, roby: -10}, wait=False)
        time.sleep(0.01)
        self.grp._Group__move_task.kill(KeyboardInterrupt, block=False)
        self.assertRaises(KeyboardInterrupt, self.grp.wait_move)
        self.assertEqual(self.grp.state(), "READY")
        self.assertEqual(robz.state(), "READY")
        self.assertEqual(roby.state(), "READY")
    
    def test_position_reading(self):
        positions_dict = self.grp.position()
        for axis, axis_pos in positions_dict.iteritems():
            group_axis = bliss.get_axis(axis.name)
            self.assertEqual(axis, group_axis)
            self.assertEqual(axis.position(), axis_pos)
    
    def test_move_done_event(self):
        res = {"ok": False}

        def callback(move_done, res=res):
            if move_done:
                res["ok"] = True
        roby = bliss.get_axis("roby")
        roby_pos = roby.position()
        robz = bliss.get_axis("robz")
        robz_pos = robz.position()
        event.connect(self.grp, "move_done", callback)
        self.grp.rmove({robz: 2, roby: 3})
        self.assertEquals(res["ok"], True)
        self.assertEquals(robz.position(), robz_pos+2)
        self.assertEquals(roby.position(), roby_pos+3)

    def test_static_move(self):
        self.grp.move(self.grp.position())
          
    def test_static_move(self):
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("robz")
        p0 = self.grp.position()
        self.grp.rmove({ robz: 0, roby: 1})
        self.assertEquals(self.grp.position()[robz], p0[robz])
        self.assertEquals(self.grp.position()[roby], p0[roby]+1)
    
    def test_bad_startone(self):
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("roby")
        roby.dial(0); roby.position(0)
        robz.dial(0); robz.position(0)
        try:
            roby.controller.set_error(True) 
            self.assertRaises(RuntimeError, self.grp.move, { robz: 1, roby: 2 }) 
            self.assertEquals(self.grp.state(), "READY")
            self.assertEquals(roby.position(), 0)
            self.assertEquals(robz.position(), 0)
        finally:
            roby.controller.set_error(False)

    def test_bad_startall(self):
        robz = bliss.get_axis("robz")
        robz2 = bliss.get_axis("robz2")
        robz2.dial(0); robz2.position(0)
        robz.dial(0); robz.position(0)
        grp = bliss.Group(robz, robz2)
        try:
            robz.controller.set_error(True)
            self.assertRaises(RuntimeError, grp.move, { robz: 1, robz2: 2})
            self.assertEquals(grp.state(), "READY")
            self.assertEquals(robz2.position(), 0)
            self.assertEquals(robz.position(), 0)
        finally:
            robz.controller.set_error(False) 

    def testHardLimitsAndSetPosition(self):
        robz = bliss.get_axis("robz")
        robz2 = bliss.get_axis("robz2")
        robz2.dial(0); robz2.position(0)
        robz.dial(0); robz.position(0)
        self.assertEquals(robz._set_position(), 0)
        grp = bliss.Group(robz, robz2)
        robz.controller.set_hw_limit(robz,-2,2)
        robz2.controller.set_hw_limit(robz2,-2,2)
        self.assertRaises(RuntimeError, grp.move, {robz:3,robz2:1})
        self.assertEquals(robz._set_position(), robz.position())

if __name__ == '__main__':
    unittest.main()
