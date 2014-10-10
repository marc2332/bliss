import unittest
import gevent
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
from bliss.common.axis import Axis

config_xml = """
<config>
  <controller class="setpoint" name="test">
    <target_attribute value="id16ni/semidyn/cyril/target_sp"/>
    <port value="5000"/>
    <axis name="sp1">
      <!-- degrees per second -->
      <velocity value="100"/>
    </axis>
  </controller>
</config>
"""

class TestSetpointController(unittest.TestCase):

    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        sp1 = bliss.get_axis("sp1")
        self.assertTrue(sp1)

if __name__ == '__main__':
    unittest.main()
