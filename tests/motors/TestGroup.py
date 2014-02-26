import unittest
import time
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

import bliss
from bliss.controllers.motor_group import Group

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <!-- degrees per second -->
      <velocity value="100"/>
    </axis>
    <axis name="robz2">
      <velocity value="100"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby">
      <backlash value="2"/>
      <step_size value="10"/>
      <velocity  value="2500"/>
    </axis>
  </controller>
  <group name="group1">
    <axis name="robz"/>
    <axis name="robz2"/>
    <axis name="roby"/>
  </group>
</config>
"""


class TestGroup(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_group_creation(self):
        grp = bliss.get_group("group1")
        self.assertTrue(grp)

    def test_group_move(self):
        robz = bliss.get_axis("robz")
        robz_pos = robz.position()
        roby = bliss.get_axis("roby")
        roby_pos = roby.position()
        grp = bliss.get_group("group1")

        self.assertEqual(grp.state(), "READY")

        target_robz = robz_pos + 50
        target_roby = roby_pos + 50
        
        move_greenlet = grp.move(robz=target_robz, roby=target_roby, wait=False)
         
        self.assertEqual(grp.state(), "MOVING")
        self.assertEqual(robz.state(), "MOVING")
        self.assertEqual(roby.state(), "MOVING")
        
        move_greenlet.join()

        self.assertEqual(robz.state(), "READY")
        self.assertEqual(roby.state(), "READY")
        self.assertEqual(grp.state(), "READY")

    def test_stop(self):
        grp = bliss.get_group("group1")
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        move_greenlet = grp.move(robz=0, roby=0, wait=False)
        self.assertEqual(grp.state(), "MOVING")
        grp.stop()
        self.assertEqual(grp.state(), "READY")
        self.assertEqual(robz.state(), "READY")
        self.assertEqual(roby.state(), "READY")

    def test_ctrlc(self):
        grp = bliss.get_group("group1")
        roby = bliss.get_axis("roby")
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        move_greenlet = grp.move(robz=0, roby=0, wait=False)
        time.sleep(0.01)
        move_greenlet.kill()
        self.assertEqual(grp.state(), "READY")
        self.assertEqual(robz.state(), "READY")
        self.assertEqual(roby.state(), "READY")
 

if __name__ == '__main__':
    unittest.main()
