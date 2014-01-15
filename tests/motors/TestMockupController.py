import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <channel value="1"/>
      <!-- degrees per second -->
      <velocity value="100"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby">
      <channel value="1"/>
      <velocity value="100"/>
    </axis>
  </controller>
  <group name="group1">
    <axis name="robz"/>
    <axis name="roby"/>
  </group>
</config>
"""

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

    def test_group_creation(self):
        grp = bliss.get_group("group1")
        self.assertTrue(grp)

    def test_axis_move(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.state(), "READY")
        move_greenlet=robz.move(180, wait=False)
        self.assertEqual(robz.state(), "MOVING")
        move_greenlet.join()
        self.assertEqual(robz.state(), "READY")

    def test_axis_init(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.settings.get("init_count"), 1)

if __name__ == '__main__':
    unittest.main()
