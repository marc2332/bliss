import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bliss

config_xml = """
<config>
  <controller class="PI_E517" name="testid16">
    <host value="e517id16ni-mlm"/>
    <axis name="pz">
    </axis>
  </controller>
</config>
"""

class TestPI_E517Controller(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_axis(self):
        pz = bliss.get_axis("pz")
        self.assertTrue(pz)

    def test_controller_from_axis(self):
        pz = bliss.get_axis("pz")
        self.assertEqual(pz.controller.name, "testid16")

    def test_get_position(self):
        pz = bliss.get_axis("pz")
        print "E517 position :", pz.position()

    def test_get_id(self):
        pz = bliss.get_axis("pz")
        print "E517 IDN :", pz.controller._get_identifier()

    def test_get_infos(self):
        pz = bliss.get_axis("pz")
        print "E517 INFOS :\n", pz.controller._get_infos()

#    # called at end of each test
#    def tearDown(self):
#        self.pz.controller.sock.close()

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

load_cfg_fromstring("""<config>
  <controller class="PI_E517" name="testid16">
    <host value="e517id16ni-mlm"/>
    <axis name="pz">
    </axis>
  </controller>
</config>
""")

a=get_axis("pz")

print a.controller.sock.write_readline("IDN?\n")
print a.controller._get_infos()



'''

'''
NA Interactive test :

load_cfg_fromstring("""<config>
  <controller class="PI_E517" name="testid16">
    <host value="e517id16na-dmir"/>
    <axis name="pz">
    </axis>
  </controller>
</config>
""")

a=get_axis("pz")

print a.controller.sock.write_readline("IDN?\n")
print a.controller._get_infos()



'''
