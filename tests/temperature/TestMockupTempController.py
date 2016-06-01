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
SP = 15
SP = 20

"""
Bliss generic library

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))
"""
"""
To work in my local dev
"""
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


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

    def test_set_rampval(self):
        SP=45
        config = static.get_config()  
        bb=config.get("heater")
        bb.rampval(SP)
        val = bb.rampval()                  
        self.assertEqual(SP,val)
         
    def test_set_stepval(self):
        SP=23
        config = static.get_config()  
        bb=config.get("heater")
        bb.stepval(SP)
        val = bb.stepval()                  
        self.assertEqual(SP,val)
         
    def test_set_dwellval(self):
        SP=12
        config = static.get_config()  
        bb=config.get("heater")
        bb.dwellval(SP)
        val = bb.dwellval()                  
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
        

    def test_output_ramp(self):
        SP=13
        config = static.get_config()  
        bb=config.get("heater")           
        val = bb.read()
        print "Ramping from %s to %s" % (val,SP)
        bb.ramp(SP)
        print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
        bb.wait()
        myval = bb.read()
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)

    def test_output_ramp_stop(self):
        SP=15
        config = static.get_config()  
        bb=config.get("heater")           
        val = bb.read()
        print "Ramping (then stopping) from %s to %s" % (val,SP)
        bb.ramp(SP)
        #gevent.sleep(3)
        #time.sleep(3)
        print ("Stopping")
        bb.stop()
        myval = bb.read()
        print "Now at: %s" % myval  

    def test_loop_output_ramp(self):
        SP=20
        config = static.get_config()  
        cc=config.get("sample_regulation")
        val = cc.output.read()
        print "Ramping from %s to %s" % (val,SP)
        cc.output.ramp(SP)
        print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
        cc.output.wait()
        myval = cc.output.read()
        print myval
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)

    def test_loop_output_ramp_stop(self):
        SP=20
        config = static.get_config()  
        cc=config.get("sample_regulation")
        val = cc.output.read()
        print "Ramping (then stopping) from %s to %s" % (val,SP)
        cc.output.ramp(SP)
        gevent.sleep(3)
        print ("Stopping")
        cc.output.stop()
        myval = cc.output.read()
        print "Now at: %s" % myval  

    def test_loop_ramp(self):
        SP=15
        config = static.get_config()  
        cc=config.get("sample_regulation")
        val = cc.output.read()
        print "Ramping from %s to %s" % (val,SP)
        cc.ramp(SP)
        print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
        cc.output.wait()
        myval = cc.output.read()
        print myval
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)

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
