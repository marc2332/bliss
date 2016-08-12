# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import gevent
import gevent.event
import time
import sys
import os
import math
import tempfile

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss
from bliss.common.axis import Axis
from bliss.common import event
from bliss.common import log

#log.level(log.DEBUG)

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <steps_per_unit value="10000"/>
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="3"/>
      <low_limit value="-1000"/>
      <high_limit value="1E9"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby" class="MockupAxis">
      <backlash value="2"/>
      <steps_per_unit value="10000"/>
      <velocity  value="2500"/>
      <acceleration value="4"/>
    </axis>
    <axis name="williams" class="MockupAxis">
      <backlash value="3"/>
      <steps_per_unit value="3000"/>
      <velocity  value="25"/>
      <acceleration value="5"/>
    </axis>
    <axis name="m0">
      <steps_per_unit value="1"/>
      <velocity  value="1000"/>
      <acceleration value="1"/>
    </axis>
  </controller>
</config>
"""

# THIS IS FOR TESTING SPECIFIC FEATURES OF AXIS OBJECTS


class MockupAxis(Axis):

    def __init__(self, *args, **kwargs):
        Axis.__init__(self, *args, **kwargs)
        self.__custom_methods_list = list()
        self.__custom_attributes_dict = dict()

    def prepare_move(self, *args, **kwargs):
        self.backlash_move = 0
        return Axis.prepare_move(self, *args, **kwargs)

    def _handle_move(self, motion, polling_time):
        self.target_pos = motion.target_pos
        self.backlash_move = motion.target_pos / \
            self.steps_per_unit if motion.backlash else 0
        return Axis._handle_move(self, motion, polling_time)


class mockup_axis_module:

    def __getattr__(self, attr):
        return MockupAxis

sys.modules["MockupAxis"] = mockup_axis_module()
###


class TestMockupController(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        robz = bliss.get_axis("robz")
        self.assertTrue(robz)

    def test_property_setting(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.velocity(), 100)

    def test_controller_from_axis(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.controller.name, "test")

    def test_state_callback(self):
        old={"state":None}
        def callback(state, old=old): #{}):
            old["state"] = state
        robz = bliss.get_axis("robz")
        event.connect(robz, "state", callback)
        robz.rmove(10, wait=False)
        while old["state"]=="MOVING":
            time.sleep(0)
        self.assertEquals(robz.state(), "READY")

    def test_position_callback(self):
        storage={"last_pos":None, "last_dial_pos":None}
        def callback(pos,old=storage):
          old["last_pos"]=pos
        def dial_callback(pos,old=storage):
          old["last_dial_pos"]=pos
        robz = bliss.get_axis("robz")
        event.connect(robz, "position", callback)
        event.connect(robz, "dial_position", dial_callback)
        robz.position(1)
        pos = robz.position()
        robz.rmove(1)
        self.assertEquals(storage["last_pos"], pos+1)
        self.assertEquals(storage["last_dial_pos"], robz.user2dial(pos+1))

    def test_rmove(self):
        robz = bliss.get_axis('robz')
        robz.move(0)
        self.assertAlmostEquals(robz.position(), 0, places=5)
        robz.rmove(0.1)
        robz.rmove(0.1)
        self.assertAlmostEquals(robz.position(), 0.2, places=5)

    def test_acceleration(self):
        robz = bliss.get_axis("robz")
        acc = robz.acceleration()
        self.assertEquals(robz.acctime(), robz.velocity()/robz.acceleration())
        v = robz.velocity()/2.0
        robz.velocity(v)
        self.assertEquals(robz.acceleration(), acc)
        self.assertEquals(robz.acctime(), v/acc)
        robz.acctime(0.03)
        self.assertEquals(robz.acceleration(), v/0.03)
        self.assertEquals(robz.acceleration(from_config=True), 3)
        robz.acceleration(acc)
        self.assertEquals(robz.acctime(), v/acc)

    def test_acceleration_2nd_ctrl(self):
        roby = bliss.get_axis("roby")
        acc = roby.acceleration()

    def test_acceleration_2nd_axis(self):
        williams = bliss.get_axis("williams")
        acc = williams.acceleration()

    def test_axis_set_acctime(self):
        roby = bliss.get_axis("roby")
        acc = 0.250
        self.assertEqual(roby.acctime(acc), acc)

    def test_move_done_event(self):
        res = {"ok": False}

        def callback(move_done, res=res):
            if move_done:
                res["ok"] = True
        robz = bliss.get_axis('robz')
        event.connect(robz, "move_done", callback)
        robz.rmove(10)
        robz.wait_move()
        self.assertEquals(res["ok"], True)

    def test_axis_move(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        robz.move(180, wait=False)
        self.assertNotEqual(robz.position(), None)
        self.assertEqual(robz.state(), "MOVING")
        robz.wait_move() 
        self.assertEqual(robz.state(), "READY")

    def test_axis_multiple_move(self):
        robz = bliss.get_axis("robz")

        for i in range(250):
            self.assertEqual(robz.state(), "READY")
            robz.move((i+1)*2, wait=False)
            self.assertEqual(robz.state(), "MOVING")
            robz.wait_move() 
            self.assertEqual(robz.state(), "READY")

    def test_axis_state(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        robz.move(180,wait=False)
        self.assertEqual(robz.state(), "MOVING")
        robz.wait_move() 
        self.assertEqual(robz.state(), "READY")
        robz.move(180,wait=False)
        self.assertEqual(robz.state(), "READY")

    def test_axis_init(self):
        robz = bliss.get_axis("robz")
        # init_count is set in initialize_axis
        ohhhy = robz.dial()
        self.assertEqual(robz.settings.get("init_count"), 1)

    def test_stop(self):
        robz = bliss.get_axis('robz')
        self.assertEqual(robz.state(), "READY")
        robz.move(180, wait=False)
        self.assertEqual(robz.state(), "MOVING")
        robz.stop()
        self.assertEqual(robz.state(), "READY")

    def test_asynchronous_stop(self):
        robz = bliss.get_axis('robz')
        self.assertEqual(robz.state(), "READY")
        robz.move(180, wait=False)
        self.assertEqual(robz.state(), "MOVING")
        robz.stop(wait=False)
        self.assertEqual(robz.state(), "MOVING")
        robz.wait_move()
        self.assertEqual(robz.state(), "READY")
        self.assertNotEqual(robz.position(), 180)

    def test_home_stop(self):
        robz = bliss.get_axis('robz')
        self.assertEqual(robz.state(), "READY")
        robz.home(wait=False)
        gevent.sleep(0.1)
        self.assertEqual(robz.state(), 'MOVING')
        robz.stop()
        robz.wait_move() 
        self.assertEqual(robz.state(), "READY")

    def test_limit_search_stop(self):
        robz = bliss.get_axis('robz')
        self.assertEqual(robz.state(), "READY")
        robz.hw_limit(1, wait=False)
        gevent.sleep(0.1)
        self.assertEqual(robz.state(), 'MOVING')
        robz.stop()
        robz.wait_move()
        self.assertEqual(robz.state(), "READY")

    def test_backlash(self):
        roby = bliss.get_axis("roby")
        self.assertEqual(roby.state(), "READY")
        roby.move(0)
        roby.move(-10, wait=False)
        time.sleep(0)
        self.assertEqual(roby.backlash_move, -12)
        roby.wait_move() 
        self.assertEqual(roby.position(), -10)
        roby.move(-9)
        roby.limits(-11, 10)
        self.assertRaises(ValueError, roby.move, -10)

    def test_limits2(self):
        robz = bliss.get_axis("robz")
        self.assertEquals(robz.limits(), (-1000,1E9))
        roby = bliss.get_axis("roby")
        self.assertEquals(roby.limits(), (None,None))
        self.assertRaises(ValueError, robz.move, -1001)

    def test_limits3(self):
        robz = bliss.get_axis("robz")
        robz.move(0)
	robz.limits(-10,10)
        robz.position(10)
        self.assertEquals(robz.limits(), (0, 20))

    def test_backlash2(self):
        roby = bliss.get_axis("roby")
        self.assertEqual(roby.state(), "READY")
        roby.move(0)
        roby.move(10, wait=False)
        time.sleep(0)
        self.assertEqual(roby.backlash_move, 0)
        roby.wait_move() 
        self.assertEqual(roby.position(), 10)

    def test_backlash3(self):
        roby = bliss.get_axis("roby")
        self.assertEqual(roby.state(), "READY")
        roby.position(1)
        self.assertEqual(roby.position(), 1)
        roby.move(1, wait=False)
        time.sleep(0)
        self.assertEqual(roby.backlash_move, 0)
        self.assertEqual(roby.position(), 1)

    def test_axis_steps_per_unit(self):
        roby = bliss.get_axis("roby")
        self.assertEqual(roby.state(), "READY")
        roby.move(180, wait=False)
        self.assertEqual(roby.state(), "MOVING")
        roby.wait_move() 
        self.assertEqual(roby.state(), "READY")
        self.assertEqual(roby.target_pos, roby.steps_per_unit * 180)

    def test_axis_set_pos(self):
        roby = bliss.get_axis("roby")
        self.assertAlmostEqual(roby.position(0), 0, places=3)
        self.assertAlmostEqual(roby.position(), 0,places=3)
        roby.position(10)
        self.assertAlmostEqual(roby.position(), 10,places=3)

    def test_axis_set_velocity(self):
        roby = bliss.get_axis("roby")
        org = roby.velocity()
        # vel is in user-unit per seconds.
        vel = 5000
        self.assertEqual(roby.velocity(vel), vel)
        roby.velocity(org)
        self.assertEqual(roby.velocity(from_config=True), 2500)

    def test_axis_config_velocity(self):
        roby = bliss.get_axis("roby")
        self.assertEqual(roby.velocity(), roby.config.get("velocity", int))

    def test_custom_method(self):
        roby = bliss.get_axis("roby")
        roby.Set_Closed_Loop(True)
        roby.Set_Closed_Loop(False)
        roby.Set_Closed_Loop()

    def test_home_search(self):
        roby = bliss.get_axis("roby")
        self.assertEqual(roby.state(), 'READY')
        roby.home(wait=False)
        self.assertEqual(roby.state(), 'MOVING')
        roby.wait_move()
        roby.dial(38930)
        roby.position(38930)
        self.assertEqual(roby.state(), 'READY')
        self.assertEqual(roby.position(), 38930)
        self.assertEqual(roby.offset, 0)

    def test_ctrlc(self):
        robz = bliss.get_axis("robz")
        final_pos = robz.position() + 100
        robz.move(final_pos, wait=False)
        self.assertEqual(robz.state(), "MOVING")
        gevent.sleep(0.5)
        robz._Axis__move_task.kill(KeyboardInterrupt, block=False)
        self.assertRaises(KeyboardInterrupt, robz.wait_move)
        self.assertEqual(robz.state(), "READY")
        self.assertTrue(robz.position() < final_pos)

    def test_limits(self):
        robz = bliss.get_axis("robz")
        low_limit = robz.position() - 1
        high_limit = robz.position() + 1
        robz.limits(low_limit, high_limit)
        self.assertEquals(robz.limits(), (low_limit, high_limit))
        self.assertRaises(ValueError, robz.move, robz.position() + 1.1)
        self.assertRaises(ValueError, robz.move, robz.position() - 1.1)
        robz.limits(-1E9, 1E9)
        robz.rmove(1)
        robz.rmove(-2)

    def test_on_off(self):
        robz = bliss.get_axis("robz")
        robz.position(0)
        robz.off()
        self.assertEquals(robz.state(), "OFF")
        self.assertRaises(RuntimeError, robz.move, 1)
        robz.on()
        self.assertEquals(robz.state(), "READY")
        robz.move(1)
        self.assertAlmostEquals(robz.position(), 1, places=5)
        robz.move(2, wait=False)
        self.assertRaises(RuntimeError, robz.off)
        robz.wait_move()
        robz.off()
        self.assertEquals(robz.state(), "OFF")

    def test_dial(self):
        robz = bliss.get_axis("robz")
        robz.move(0)
        robz.position(1)
        self.assertEquals(robz.dial(), 0)
        self.assertEquals(robz.position(), 1)
        robz.position(robz.dial())
        self.assertEquals(robz.position(), 0)
        robz.dial(1)
        self.assertEquals(robz.dial(), 1)
        self.assertEquals(robz.position(), 0)
        robz.dial(2)
        robz.position(2)
        self.assertEquals(robz.dial(), 2)
        self.assertEquals(robz.position(), 2)

    def test_limit_search(self):
        robz = bliss.get_axis("robz")
        robz.hw_limit(1)
        self.assertEquals(robz.dial(), 1E6)
        robz.hw_limit(-1)
        self.assertEquals(robz.dial(), -1E6)
        robz.hw_limit(1)
        robz.dial(10)
        robz.position(10)
        self.assertEquals(robz.dial(), 10)
        self.assertEquals(robz.position(), 10)

    def test_set_position(self):
        m0 = bliss.get_axis("m0")
        m0.position(0)
        self.assertEquals(m0.position(), m0._set_position())
        m0.rmove(0.1)
        self.assertEquals(m0.position(), 0)
        self.assertEquals(m0._set_position(), 0.1)
        for i in range(9):
            m0.rmove(0.1)
        self.assertAlmostEqual(m0._set_position(), 1.0)
        self.assertAlmostEqual(m0.position(), m0._set_position())
        m0.move(0.4)
        self.assertEquals(m0._set_position(), 0.4)
        self.assertEquals(m0.position(), 0)
        m0.rmove(0.6)
        self.assertAlmostEqual(m0._set_position(), 1)
        self.assertAlmostEqual(m0.position(), m0._set_position())
        m0.move(2, wait=False)
        time.sleep(0.01)
        m0._Axis__move_task.kill(KeyboardInterrupt)
        try:
            m0.wait_move()
        except KeyboardInterrupt:
            pass
        m0.move(1)
        self.assertEquals(m0._set_position(), 1)
    
    def test_interrupted_waitmove(self):
        m0 = bliss.get_axis("m0")
        m0.position(0)
        m0.move(100,wait=False)
        waitmove = gevent.spawn(m0.wait_move)
        time.sleep(0.01)
        try:
            waitmove.kill(KeyboardInterrupt)
        except:
            self.assertEquals(m0.state(), "READY")

    def test_hardware_limits(self):
        m = bliss.get_axis("roby")
        m.dial(0);m.position(0)
        m.controller.set_hw_limit(m, -2,2)
        self.assertRaises(RuntimeError, m.move, 3)
        self.assertEquals(m.position(), 2)
        # move hit limit because of backlash
        self.assertRaises(RuntimeError, m.move, 0)
        m.move(1)
        self.assertEquals(m.position(), 1)
        self.assertRaises(RuntimeError, m.move, -3)
        self.assertEquals(m.position(), -2)

    def test_bad_start(self):
        m = bliss.get_axis("roby")
        m.dial(0); m.position(0)
        try:
            m.controller.set_error(True)
            self.assertRaises(RuntimeError, m.move, 1)
            self.assertEquals(m.state(), "READY")
            self.assertEquals(m.position(), 0)
        finally:
            m.controller.set_error(False)     

    def test_no_offset(self):
        m = bliss.get_axis("roby")
        m.no_offset = True
        m.move(0)
        m.position(1)
        self.assertEquals(m.dial(), 1)
        m.dial(0)
        self.assertEquals(m.position(), 0)

    def test_settings_to_config(self):
        m = bliss.get_axis("roby")
        m.velocity(3)
        m.acceleration(10)
        self.assertEquals(m.velocity(from_config=True), 2500) 
        self.assertEquals(m.acceleration(from_config=True), 4)
        m.settings_to_config()
        self.assertEquals(m.velocity(from_config=True), 3) 
        self.assertEquals(m.acceleration(from_config=True), 10)

    def test_apply_config(self):
        m = bliss.get_axis("roby")
        m.velocity(3)
        m.acceleration(10)
        m.limits(0,10)
        m.apply_config()
        self.assertEquals(m.velocity(), 2500)        
        self.assertEquals(m.acceleration(), 4)        
        self.assertEquals(m.limits(), (None,None))
    
    def test_reload_config(self):
        cfg="""
            <config>
              <controller class='mockup'>
                <axis name="m0">
                  <velocity value="1000"/>
                  <acceleration value="100"/>
                  <low_limit value="-5"/>
                  <high_limit value="5"/>
                </axis>
              </controller>
            </config>
        """
        f = tempfile.NamedTemporaryFile()
        filename = f.name
        try:
            f.write(cfg) 
            f.flush()
            bliss.load_cfg(f.name)
            m = bliss.get_axis("m0")
            self.assertEquals(m.config.config_dict.config_file, f.name)
        finally:
            f.close()
        self.assertEquals(m.limits(), (-5,5))
        self.assertEquals(m.backlash, 0)
        self.assertEquals(m.steps_per_unit, 1)
        cfg2 = """
            <config>
              <controller class='mockup'>
                <axis name="m0">
                  <steps_per_unit value="5"/>
                  <velocity value="1000"/>
                  <acceleration value="100"/>
                  <low_limit value="-5"/>
                  <high_limit value="10"/>
                  <backlash value="4"/>
                </axis>
              </controller>
            </config>
        """
        with open(filename, "w") as f:
            f.write(cfg2)
        try:
            m.config.reload()
        
            self.assertEquals(m.config.config_dict['high_limit']['value'], '10')
            self.assertEquals(m.backlash, 4)
            self.assertEquals(m.steps_per_unit, 5)
            m.apply_config()
            self.assertEquals(m.limits(), (-5,10))
        finally:
            os.unlink(filename)

       

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMockupController)
    unittest.TextTestRunner(verbosity=2).run(suite)
    #unittest.main()
