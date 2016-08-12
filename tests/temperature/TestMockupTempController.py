# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import sys
import os
import optparse
import re
import signal
import gevent
import pdb
import time

SP = 10
KW = 1

"""
Bliss generic library
"""

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

"""
.yml file used for unitest:
in lid269:blissadm/local/beamline_configuration/temp/test.yml
-----------------------------------
controller:
    class: mockup
    host: lid269
    inputs:
        - 
            name: thermo_sample
            channel: A
            unit: deg
            tango_server: temp1
        - 
            name: sensor
            channel: B
            tango_server: temp1
    outputs: 
        -
            name: heater
            channel: B 
            unit: deg
            low_limit: 10
            high_limit: 200
            deadband: 0.1
            tango_server: temp1
    ctrl_loops:
        -
            name: sample_regulation
            input: $thermo_sample
            output: $heater
            P: 2.2
            I: 1.1
            D: 0.1
            frequency: 2
            deadband: 5
            tango_server: temp1
------------------------------------
"""


import bliss
from bliss.common import log;
from bliss.config import static

"""
UnitTest list of tests
"""


class TestMockupTempController(unittest.TestCase):

    # called for each test
    def setUp(self):
        pass

    # called at the end of each individual test
    def tearDown(self):
        pass

    def test_creation_input(self):
        config = static.get_config()     
        aa=config.get("thermo_sample")
        self.assertTrue(aa)

    def test_creation_output(self):
        config = static.get_config()     
        bb=config.get("heater")
        self.assertTrue(bb)

    def test_creation_loops(self):       
        config = static.get_config()     
        cc=config.get("sample_regulation")
        self.assertTrue(cc)

    def test_read_input(self):       
        config = static.get_config()     
        aa=config.get("thermo_sample")
        print "%s" % (aa.read())            

    def test_input_state(self):
        config = static.get_config()     
        aa=config.get("thermo_sample")
        aa.state() 

    def tests_output_state(self):
        config = static.get_config()     
        bb=config.get("heater")
        bb.state() 

    def tests_output_limits(self):
        config = static.get_config()     
        bb=config.get("heater")
        self.assertEqual(10,bb.limits[0])
        self.assertEqual(200,bb.limits[1])

    def tests_output_deadband(self):
        config = static.get_config()     
        bb=config.get("heater")
        self.assertEqual(0.1,bb.deadband)

    def test_read_output(self):       
        config = static.get_config()     
        bb=config.get("heater") 
        print "%s" % (bb.read())   

    def test_read_input_from_loop(self):       
        config = static.get_config()     
        cc=config.get("sample_regulation")
        print "%s" % (cc.input.read())   

    def test_read_output_from_loop(self):       
        config = static.get_config()     
        cc=config.get("sample_regulation")
        print "%s" % (cc.output.read())  

    def test_set_ramprate(self):
        SP=45
        config = static.get_config()  
        bb=config.get("heater")
        bb.ramprate(SP)
        val = bb.ramprate()                  
        self.assertEqual(SP,val)
         
    def test_set_stepval(self):
        SP=23
        config = static.get_config()  
        bb=config.get("heater")
        bb.step(SP)
        val = bb.step()                  
        self.assertEqual(SP,val)
         
    def test_set_dwell(self):
        SP=12
        config = static.get_config()  
        bb=config.get("heater")
        bb.dwell(SP)
        val = bb.dwell()                  
        self.assertEqual(SP,val) 

    def test_output_set(self):
        SP=10
        config = static.get_config()  
        bb=config.get("heater")           
        val = bb.read()
        print "Direct setpoint from %s to %s" % (val,SP)
        bb.set(SP)
        bb.wait()
        myval = bb.read()
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)
        myset = bb.set()
        self.assertAlmostEqual(int(round(myset)),SP,places=1)

    def test_output_set_with_kwarg(self):
        SP=11
        KW=23
        config = static.get_config()  
        bb=config.get("heater")           
        val = bb.read()
        print "Direct setpoint from %s to %s" % (val,SP)
        bb.set(SP, step=KW)
        bb.wait()
        myval = bb.read()
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)
        myset = bb.set()
        self.assertAlmostEqual(int(round(myset)),SP,places=1)
        myval = bb.step()
        self.assertEqual(myval,KW)

        
    def test_loop_set(self):
        SP=18
        config = static.get_config()  
        cc=config.get("sample_regulation")
        val = cc.output.read()
        print "Direct setpoint from %s to %s" % (val,SP)
        cc.set(SP)
        cc.output.wait()
        myval = cc.output.read()
        print myval
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)


    def test_loop_regulation(self):
        config = static.get_config()  
        cc=config.get("sample_regulation")
        print "starting regulation"
        cc.on()
        print "Stopping regulation"
        cc.off()

    def test_kp(self):
        KW=13
        config = static.get_config()  
        cc=config.get("sample_regulation")
        print "Setting P to %f" % KW
        cc.kp(KW)
        myval = cc.kp()
        self.assertEqual(KW,myval)
        
    def test_ki(self):
        KW=50
        config = static.get_config()  
        cc=config.get("sample_regulation")
        print "Setting I to %f" % KW
        cc.ki(KW)
        myval = cc.ki()
        self.assertEqual(KW,myval)
        
    def test_kd(self):
        KW=1
        config = static.get_config()  
        cc=config.get("sample_regulation")
        print "Setting D to %f" % KW
        cc.kd(KW)
        myval = cc.kd()
        self.assertEqual(KW,myval)
        
    def test_read_input_counters(self):       
        config = static.get_config()     
        aa=config.get("thermo_sample")
        myval = aa.read()
        print "%s" % (myval) 
        myvalcount = aa.counters.read()
        self.assertAlmostEqual(myval,myvalcount,places=1)

    def test_read_output_counters(self):       
        config = static.get_config()     
        bb=config.get("heater")
        myval = bb.read()
        print "%s" % (myval) 
        myvalcount = bb.counters.read()
        self.assertAlmostEqual(myval,myvalcount,places=1)
           
           
               
"""
Main entry point
"""
if __name__ == '__main__':


    # Launch the tests sequence
    print "\nTesting Mockup Temperature controller\n"
    print "\n".rjust(70, "-")

    # Change the default unittest test sequence order from cmp() to line number
    loader = unittest.TestLoader()
    ln = lambda f: getattr(TestMockupTempController, f).\
        im_func.func_code.co_firstlineno
    lncmp = lambda a, b: cmp(ln(a), ln(b))
    loader.sortTestMethodsUsing = lncmp

    # NOTE: unittest.main(verbosity=2) not supported under Python 2.6
    suite  = loader.loadTestsFromTestCase(TestMockupTempController)
    unittest.TextTestRunner(verbosity=3).run(suite)

    # normal end
