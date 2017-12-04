# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os
import time

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss

config_xml = """
<config>
  <controller class="PI_E753" name="testid16">
    <host value="e753id16ni-mlm"/>
    <axis name="pz">
    </axis>
  </controller>
</config>
"""


class TestPI_E753Controller(unittest.TestCase):

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
        print "E753 position :", pz.position()

    def test_get_id(self):
        pz = bliss.get_axis("pz")
        print "E753 IDN :", pz.controller._get_identifier()

    def test_get_info(self):
        pz = bliss.get_axis("pz")
        print "E753 INFOS :\n", pz.controller._get_info()

    # called at end of each test
    def tearDown(self):
        # Little wait time to let time to PI controller to
        # close peacefully its sockets ???
        time.sleep(0.05)

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
  <controller class="PI_E753" name="testid16">
    <host value="e753id16ni-mlm"/>
    <axis name="pz">
    </axis>
  </controller>
</config>
""")

a=get_axis("pz")

print a.controller.sock.write_readline("IDN?\n")
print a.controller._get_info()



'''

'''
NA Interactive test :

load_cfg_fromstring("""<config>
  <controller class="PI_E753" name="testid16">
    <host value="e753id16na-dmir"/>
    <axis name="pz">
    </axis>
  </controller>
</config>
""")

a=get_axis("pz")

print a.controller.sock.write_readline("IDN?\n")
print a.controller._get_info()



'''
