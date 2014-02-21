import unittest
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss

config_xml = """
<config>
  <controller class="PI_E517" name="testid16">
    <host value="e517pela"/>
    <axis name="px">
      <channel       value="1"/>
      <chan_letter   value="A"/>
      <velocity      value="12"/>
    </axis>
    <axis name="py">
      <channel       value="2"/>
      <chan_letter   value="B"/>
      <velocity      value="12"/>
    </axis>
    <axis name="pz">
      <channel       value="3"/>
      <chan_letter   value="C"/>
      <velocity      value="12"/>
    </axis>
  </controller>
</config>
"""

class TestPI_E517Controller(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_id(self):
        pz = bliss.get_axis("pz")
        print "E517 IDN :", pz.get_id()

    def test_get_position(self):
        pz = bliss.get_axis("pz")
        print "E517 pz position :", pz.position()

    def test_get_axis(self):
        pz = bliss.get_axis("pz")
        self.assertTrue(pz)

    def test_get_state(self):
        pz = bliss.get_axis("pz")
        print "E517 pz state:", pz.state()

    def test_get_infos(self):
        pz = bliss.get_axis("pz")
        print "E517 INFOS :\n", pz.get_infos()

    def test_get_voltage(self):
        pz = bliss.get_axis("pz")
        print "E517 pz output voltage :", pz.controller._get_voltage(pz)

    def test_get_closed_loop_status(self):
        pz = bliss.get_axis("pz")
        print "E517 pz closed loop enabled :", pz.controller._get_closed_loop_status(pz)

    def test_get_on_target_status(self):
        pz = bliss.get_axis("pz")
        print "E517 pz on target :", pz.controller._get_on_target_status(pz)

    # called at end of each test
    def tearDown(self):
        # Little wait time to let time to PI controller to
        # close peacefully its sockets...
        time.sleep(0.2)

#     def test_axis_move(self):
#         pz = bliss.get_axis("pz")
#         self.assertEqual(pz.state(), "READY")
#         move_greenlet=pz.move(10, wait=False)
#         self.assertEqual(pz.state(), "MOVING")
#         move_greenlet.join()
#         self.assertEqual(pz.state(), "READY")

if __name__ == '__main__':
    unittest.main()


'''
NI Interactive test :

load_cfg_fromstring("""
<config>
  <controller class="PI_E517" name="testid16">
    <host value="e517pela"/>
    <axis name="px">
      <channel       value="1"/>
      <chan_letter   value="A"/>
      <velocity      value="12"/>
    </axis>
    <axis name="py">
      <channel       value="2"/>
      <chan_letter   value="B"/>
      <velocity      value="12"/>
    </axis>
    <axis name="pz">
      <channel       value="3"/>
      <chan_letter   value="C"/>
      <velocity      value="12"/>
    </axis>
  </controller>
</config>
""")

a=get_axis("px")
b=get_axis("py")
c=get_axis("pz")



'''

