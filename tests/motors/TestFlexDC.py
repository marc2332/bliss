import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss

config_xml = """
<config>
  <controller class="FlexDC" name="id16phn">
    <host value="flexdcnina"/>
    <axis name="fd">
      <channel value="X"/>
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


#    def test_get_position(self):
#        fd = bliss.get_axis("fd")
#        print "FlexDC position :", fd.position()

    def test_get_id(self):
        fd = bliss.get_axis("fd")
        print "FlexDC ID :", fd.controller._get_id(fd.channel)

    def test_get_velocity(self):
        fd = bliss.get_axis("fd")
        print "FlexDC valocity :", fd.velocity()

    def test_get_infos(self):
        fd = bliss.get_axis("fd")
        print "FlexDC INFOS :\n", fd.controller._get_infos(fd.channel)

#    # called at end of each test
#    def tearDown(self):
#        self.fd.controller.sock.close()

#     def test_axis_move(self):
#         fd = bliss.get_axis("fd")
#         self.assertEqual(fd.state(), "READY")
#         move_greenlet=fd.move(10, wait=False)
#         self.assertEqual(fd.state(), "MOVING")
#         move_greenlet.join()
#         self.assertEqual(fd.state(), "READY")

if __name__ == '__main__':
    unittest.main()



'''
NA Interactive test :

load_cfg_fromstring("""<config>
  <controller class="FlexDC" name="id16phn">
    <host value="flexdcnina"/>
    <axis name="fd">
      <channel value="X"/>
    </axis>
  </controller>
</config>
""")

a=get_axis("fd")

print a.controller._flexdc_get_id()


# print a.controller.sock.write_readline("\n")

'''
