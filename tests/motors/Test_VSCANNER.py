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
from bliss.common import log as elog


# using 0-100 scale (ex microns of a piezo)
# velocity : 1.3 um / s
config_xml = """
<config>
  <controller class="VSCANNER" name="test_VSCAN_R">
    <serial_line value = "/dev/ttyS0" />
    <axis name="px">
      <velocity value="1.3" />
      <chan_letter value="X"/>
      <steps_per_unit value="0.1"/>
    </axis>
    <axis name="py">
      <velocity value="12" />
      <chan_letter value="Y"/>
      <steps_per_unit value="0.1"/>
    </axis>
  </controller>
</config>
"""


class Test_VSCANNER_Controller(unittest.TestCase):

    # called for each test
    def setUp(self):
        # elog.level(10)
        bliss.load_cfg_fromstring(config_xml)

    def test_get_id(self):
        print "################### get_id ###############"
        px = bliss.get_axis("px")
        print "ID :", px.get_id()
        print "SPU: ", px.config.get("steps_per_unit")

    def test_get_id(self):
        print "################### get_velocity ###############"
        px = bliss.get_axis("px")
        _vel = px.velocity()
        print "px velocity: ", _vel

    def test_get_chan(self):
        print "################### get_chan ###############"
        px = bliss.get_axis("px")
        print "VSCANNER px chan_letter :", px.chan_letter
        py = bliss.get_axis("py")
        print "VSCANNER py chan_letter :", py.chan_letter

    def test_get_position(self):
        print "################### get_position ###############"
        px = bliss.get_axis("px")
        print "VSCANNER px position :", px.position()
        py = bliss.get_axis("py")
        print "VSCANNER py position :", py.position()

    def test_get_state(self):
        print "################### get_state ###############"
        px = bliss.get_axis("px")
        print "VSCANNER px state:", px.state()
        py = bliss.get_axis("py")
        print "VSCANNER py state:", py.state()

    def test_get_info(self):
        print "################### get_info ###############"
        px = bliss.get_axis("px")
        print "VSCANNER INFOS :\n", px.get_info()

    def test_move(self):
        print "################### move ###############"
        px = bliss.get_axis("px")
        _pos = px.position()
        print "VSCANNER px.position = %g" % _pos
        if _pos < 88:
            _new_pos = _pos + 11.11
        else:
            _new_pos = 0
        print "VSCANNER move to ", _new_pos
        px.move(_new_pos)
        print "VSCANNER new pos : ", px.position()

if __name__ == '__main__':
    unittest.main()


'''
Interactive test :

load_cfg_fromstring("""
<config>
  <controller class="VSCANNER" name="VS_POOL">
    <axis name="p1">
      <chan_letter value="X" />
      <velocity value="10" />
      <steps_per_unit value="1" />
    </axis>
    <axis name="p2">
      <chan_letter value="Y" />
      <velocity value="10" />
      <steps_per_unit value="1" />
    </axis>
  </controller>
</config>
""");

a=get_axis("p1")
b=get_axis("p2")

'''
