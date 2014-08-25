import unittest
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

import bliss
from bliss.common.axis import Axis

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <!-- degrees per second -->
      <velocity value="100"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby" class="MockupAxis">
      <backlash value="2"/>
      <steps_per_unit value="10"/>
      <velocity  value="2500"/>
    </axis>
  </controller>
</config>
"""

# THIS IS FOR TESTING SPECIFIC FEATURES OF AXIS OBJECTS


class MockupAxis(Axis):

    def __init__(self, *args, **kwargs):
        Axis.__init__(self, *args, **kwargs)

    def _handle_move(self, motion):
        self.target_pos = motion.target_pos
        self.backlash_move = motion.target_pos / \
            self.steps_per_unit() if motion.backlash else 0
        return Axis._handle_move(self, motion)


class mockup_axis_module:

    def __getattr__(self, attr):
        return MockupAxis

sys.modules["MockupAxis"] = mockup_axis_module()


class TestMockupController(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        robz = bliss.get_axis("robz")
        self.assertTrue(robz)

    def test_get_custom_methods_list(self):
        robz = bliss.get_axis("robz")
        print "\ncustom functions :"
        for (fname, types) in robz.custom_methods_list:
            print fname, types

    def test_custom_park(self):
        robz = bliss.get_axis("robz")
        robz.custom_park()

    def test_custom_get_forty_two(self):
        robz = bliss.get_axis("robz")
        print robz.custom_get_forty_two()

    def test_custom_get_twice(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.custom_get_twice(42), 84)

    def test_custom_get_chapi(self):
        robz = bliss.get_axis("robz")
        self.assertEqual(robz.custom_get_chapi("chapi"), "chapo")
        self.assertEqual(robz.custom_get_chapi("titi"), "toto")
        self.assertEqual(robz.custom_get_chapi("roooh"), "bla")

    def test_custom_send_command(self):
        robz = bliss.get_axis("robz")
        robz.custom_send_command("SALUT sent")


if __name__ == '__main__':
    unittest.main()
