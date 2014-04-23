import unittest
import sys
import os
import time

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

import bliss

config_xml = """
<config>
  <controller class="PM206" name="id16pm206">
    <host value="pm206id16ni1"/>
    <axis name="pm1">
      <channel            value="1"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm2">
      <channel       value="2"/>
    </axis>
  </controller>
</config>
"""


class TestPM206Controller(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_chan(self):
        pm1 = bliss.get_axis("pm1")
        print "PM206 channel :", pm1.channel

    def test_get_info(self):
        pm1 = bliss.get_axis("pm1")
        print "PM206 info :"
        print pm1.get_info()

    # called at end of each test
    def tearDown(self):
        # Little wait time to let time to PM206 controller to
        # close peacefully its sockets... (useful ?)
        time.sleep(0.2)


if __name__ == '__main__':
    unittest.main()




'''
interactive test:



load_cfg_fromstring("""
<config>
  <controller class="PM206" name="id16pm206">
    <host value="pm206id16ni1"/>
    <axis name="pm1">
      <channel            value="1"/>
      <steps_per_unit     value="65536"/>
      <stop_range         value="10"/>
      <encoder_direction  value="1"/>
      <minimum_speed      value="2"/>
      <maximum_speed      value="32"/>
      <velocity           value="30"/>
    </axis>
    <axis name="pm2">
      <channel       value="2"/>
    </axis>
  </controller>
</config>
""")
p = get_axis("pm1")


