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
  <controller class="PI_E517" name="testid16a">
    <host value="192.168.167.10"/>
    <encoder name="encA">
      <steps_per_unit value="1"/>
      <tolerance value="0.001"/>
    </encoder>
    <axis name="px">
      <channel       value="1"/>
      <chan_letter   value="A"/>
    </axis>
    <axis name="py">
      <channel       value="2"/>
      <chan_letter   value="B"/>
    </axis>
    <axis name="pz">
      <channel       value="3"/>
      <chan_letter   value="C"/>
    </axis>
  </controller>
</config>
"""


class TestPI_E517Controller(unittest.TestCase):

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml)

    def test_get_informations(self):
        pz = bliss.get_axis("pz")
        print "PI_E517 IDN :", pz.get_id()
        print "PI_E517 channel :", pz.channel
        print "PI_E517 chan_letter :", pz.chan_letter
        print "PI_E517 pz state:", pz.state()
        print "PI_E517 INFOS :\n", pz.get_info()

    def test_get_position(self):
        pz = bliss.get_axis("pz")
        print "PI_E517 pz position :", pz.position()
        print "PI_E517 pz measured position :", pz.measured_position()
        print "PI_E517 pz output voltage :", pz.controller._get_voltage(pz)

    def test_get_closed_loop_status(self):
        pz = bliss.get_axis("pz")
        print "PI_E517 pz closed loop enabled :", \
              pz.controller._get_closed_loop_status(pz)

    def test_very_small_move(self):
        pz = bliss.get_axis("pz")
        _pos = pz.position()
        _new_pos = _pos + 0.001
        print "PI_E517 move to ",  _new_pos
        pz.move(_new_pos)

    def test_encoder(self):
        encA = bliss.get_encoder("encA")
        self.assertTrue(encA)
        print "PI_E517 encoder : ", encA.read()

#    def test_multiple_move(self):
#        pz = bliss.get_axis("pz")
#        _pos = pz.position()
#        for i in range(1000):
#            print i,
#            pz.move(_pos, wait=True)
#
#    def test_multiple_raw_move(self):
#        pz = bliss.get_axis("pz")
#        _pos = pz.position()
#        _cmd = "SVA %s %g \n" % (pz.chan_letter, _pos)
#        for i in range(1000):
#            print i,
#            pz.controller.sock.write(_cmd)
#            # time.sleep(0.001)
#        _pos = pz.position()
#        print "PI_E517 pos=", _pos
#
#
#    def test_multiple_raw_read_pos(self):
#        '''
#        25 mar.2014 :
#        nb_cmd=10000, mean=1.217250ms, max=2.267838 Ran 1 test in 12.414s
#        nb_cmd=100000,mean=1.242071ms, max=919.186115
#               val> 4ms : 627.511 919.186 887.565
#        '''
#        pz = bliss.get_axis("pz")
#        _cmd = "SVA? %s\n" % pz.chan_letter
#        _sum_time = 0
#        _nb_cmd = 100000
#        _max_duration = 0
#        _errors = 0
#        for i in range(_nb_cmd):
#            _t0 = time.time()
#            try:
#                _pos = pz.controller.sock.write_readline(_cmd, timeout=0.1),
#            except:
#                import pdb
#                pdb.set_trace()
#                print "TIMEOUT"
#            _duration = (time.time() - _t0) *1000
#            _sum_time = _sum_time + _duration
#            if _duration > _max_duration:
#                _max_duration = _duration
#            if _duration > 5:
#                print "i=%d  %6.3f" % (i, _duration)
#                _errors = _errors + 1
#            if (i % 100) == 0:
#                print ".",
#        print "nb_cmd=%d, mean=%fms, max=%f" % (_nb_cmd, _sum_time / _nb_cmd, _max_duration)
#
#
#     def test_multiple_raw_read_pos_and_move(self):
#         print " \n\n"
#         pz = bliss.get_axis("pz")
#         _pos = pz.position()
#         _cmd_move = "SVA %s %g \n" % (pz.chan_letter, _pos)
#         _cmd_pos = "SVA? %s\n" % pz.chan_letter
#         for i in range(100):
#             print i,
#             print pz.controller.sock.write_readline(_cmd_pos),
#             # time.sleep(0.01)
#             pz.controller.sock.write(_cmd_move)
#
#
#    def test_multiple_raw_read_pos_and_move_3chan(self):
#        print " \n\n"
#        px = bliss.get_axis("px")
#        py = bliss.get_axis("py")
#        pz = bliss.get_axis("pz")
#        _pos_x = px.position()
#        _pos_y = py.position()
#        _pos_z = pz.position()
#        _cmd_move_x = "SVA %s %g \n" % (px.chan_letter, _pos_x)
#        _cmd_pos_x = "SVA? %s\n" % px.chan_letter
#        _cmd_move_y = "SVA %s %g \n" % (py.chan_letter, _pos_y)
#        _cmd_pos_y = "SVA? %s\n" % py.chan_letter
#        _cmd_move_z = "SVA %s %g \n" % (pz.chan_letter, _pos_z)
#        _cmd_pos_z = "SVA? %s\n" % pz.chan_letter
#
#        _respire = 0
#
#        for i in range(100):
#            print i,
#
#            _t0 = time.time()
#            px.controller.sock.write(_cmd_move_x)
#            _ans = px.controller.sock.write_readline(_cmd_pos_x)
#            _duration = 1000 * (time.time() - _t0)
#            print _ans,
#            if _duration > 5:
#                print "oups duration : ", _duration
#            time.sleep(_respire)
#
#            _t0 = time.time()
#            py.controller.sock.write(_cmd_move_y)
#            _ans = py.controller.sock.write_readline(_cmd_pos_y)
#            _duration = 1000 * (time.time() - _t0)
#            print _ans,
#            if _duration > 5:
#                print "oups duration : ", _duration
#            time.sleep(_respire)
#
#            _t0 = time.time()
#            pz.controller.sock.write(_cmd_move_z)
#            _ans =  pz.controller.sock.write_readline(_cmd_pos_z)
#            _duration = 1000 * (time.time() - _t0)
#            print _ans,
#            if _duration > 5:
#                print "oups duration : ", _duration
#            time.sleep(_respire)


    def test_get_on_target_status(self):
        pz = bliss.get_axis("pz")
        print "PI_E517 pz on target :", pz.controller._get_on_target_status(pz)

    # called at end of each test
    def tearDown(self):
        # Little wait time to let time to PI controller to
        # close peacefully its sockets... (useful ?)
        time.sleep(0.2)



if __name__ == '__main__':
    unittest.main()


'''
NI Interactive test :

load_cfg_fromstring("""
<config>
  <controller class="PI_E517" name="testid16a">
    <host value="192.168.167.10"/>
    <axis name="p4">
      <channel       value="1"/>
      <chan_letter   value="A"/>
    </axis>
    <axis name="p5">
      <channel       value="2"/>
      <chan_letter   value="B"/>
    </axis>
    <axis name="p6">
      <channel       value="3"/>
      <chan_letter   value="C"/>
    </axis>
  </controller>
  <controller class="PI_E517" name="testid16b">
    <host value="192.168.168.10"/>
    <axis name="p1">
      <channel       value="1"/>
      <chan_letter   value="A"/>
    </axis>
    <axis name="p2">
      <channel       value="2"/>
      <chan_letter   value="B"/>
    </axis>
    <axis name="p3">
      <channel       value="3"/>
      <chan_letter   value="C"/>
    </axis>
  </controller>
</config>
""")

d=get_axis("p4")
e=get_axis("p5")
f=get_axis("p6")


load_cfg_fromstring("""
<config>
  <controller class="PI_E517" name="e517b">
    <host value="192.168.168.10" />
    <axis name="p1">
      <channel value="1" />
      <chan_letter value="A" />
      <velocity value="10" />
      <steps_per_unit value="1" />
    <settings><velocity value="10.0" /><position value="20.3624" /><low_limit value="-1000000000.0" /><high_limit value="1000000000.0" /></settings></axis>
    <axis name="p2">
      <channel value="2" />
      <chan_letter value="B" />
      <velocity value="10" />
      <steps_per_unit value="1" />
    <settings><velocity value="10.0" /><position value="38.3457" /><low_limit value="-1000000000.0" /><high_limit value="1000000000.0" /></settings></axis>
    <axis name="p3">
      <channel value="3" />
      <chan_letter value="C" />
      <velocity value="10" />
      <steps_per_unit value="1" />
    <settings><velocity value="10.0" /><position value="-0.3161" /><low_limit value="-1000000000.0" /><high_limit value="1000000000.0" /></settings></axis>
  </controller>
</config>
""") ; 


a=get_axis("p1")
b=get_axis("p2")
c=get_axis("p3")


'''
