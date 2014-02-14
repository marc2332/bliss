"""
Unittest for FlexDC controller in bliss library.
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss

config_xml = """
<config>
  <controller class="FlexDC" name="id16phn">
    <host value="flexdcnina"/>
    <axis name="fd">
      <channel       value="X"/>
      <step_size     value="13111"/>
      <target_radius value="20"/>
      <target_time   value="10"/>
      <smoothing     value="4"/>
      <acceleration  value="1111"/>
      <deceleration  value="1010"/>
      <velocity      value="1234"/>
    </axis>
  </controller>
</config>
"""

class TestFlexDCController(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        fd = bliss.get_axis("fd")
        self.assertTrue(fd)

    def test_controller_from_axis(self):
        fd = bliss.get_axis("fd")
        self.assertEqual(fd.controller.name, "id16phn")

    def test_state(self):
        fd = bliss.get_axis("fd")
        print "FlexDC state :", fd.state()

    def test_position(self):
        fd = bliss.get_axis("fd")
        print "FlexDC position :", fd.position()

    def test_get_id(self):
        fd = bliss.get_axis("fd")
        print "FlexDC ID :", fd.get_id()

    def test_velocity(self):
        fd = bliss.get_axis("fd")
        _read_vel = fd.velocity()
        print "FlexDC read velocity :",  _read_vel
        self.assertEqual(_read_vel, 1234)

    def test_get_info(self):
        fd = bliss.get_axis("fd")
        print "FlexDC INFOS :\n", fd.get_info()

    # called at end of each test
    def tearDown(self):
        # Little wait time to let time to flexdc controller to
        # close peacefully its sockets...
        time.sleep(0.05)

#    def test_axis_move(self):
#        fd = bliss.get_axis("fd")
#        self.assertEqual(fd.state(), "READY")
#        move_greenlet=fd.move(10, wait=False)
#        self.assertEqual(fd.state(), "MOVING")
#        move_greenlet.join()
#        self.assertEqual(fd.state(), "READY")

if __name__ == '__main__':
    unittest.main()



'''
NINA Interactive test :

load_cfg_fromstring("""<config>
  <controller class="FlexDC" name="id16phn">
    <host value="flexdcnina"/>
    <axis name="fd">
      <channel       value="X"/>
      <step_size     value="13111"/>
      <target_radius value="20"/>
      <target_time   value="10"/>
      <smoothing     value="4"/>
      <acceleration  value="1111"/>
      <deceleration  value="1010"/>
      <velocity      value="1234"/>
    </axis>
  </controller>
</config>
""");  a=get_axis("fd")  ; print a.state()


print a.get_id()

print a.get_info()

print a.controller


'''
