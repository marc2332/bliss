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

config_xml = """
<config>
  <controller class="mockup" name="test">
    <host value="mydummyhost1"/>
    <port value="5000"/>
    <axis name="robz">
      <!-- degrees per second -->
      <velocity value="100"/>
      <acceleration value="1"/>
      <cust_attr_float_init value="3.14"/>
    </axis>
  </controller>
  <controller class="mockup">
    <host value="mydummyhost2"/>
    <port value="5000"/>
    <axis name="roby">
      <backlash value="2"/>
      <steps_per_unit value="10"/>
      <velocity  value="2500"/>
      <acceleration value="1"/>
    </axis>
  </controller>
</config>
"""

class TestMockupController(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        robz = bliss.get_axis("robz")
        self.assertTrue(robz)

    def test_custom_attribute_read(self):
        robz = bliss.get_axis("robz")
        # print robz.dial()
        self.assertAlmostEquals(robz.get_cust_attr_float(), 3.14, places=4)
        robz.set_cust_attr_float(7.20)
        self.assertAlmostEquals(robz.get_cust_attr_float(), 7.20, places=4)

#    def test_custom_attribute_rw(self):
#        robz = bliss.get_axis("robz")
#        self.assertEqual(robz.voltage, 220)
#        robz.voltage = 380
#        self.assertEqual(robz.voltage, 380)
#        robz.voltage = 220
#        self.assertEqual(robz.voltage, 220)


if __name__ == '__main__':
    unittest.main()
