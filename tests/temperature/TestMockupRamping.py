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
"""

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))


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

    def test_output_ramp_with_kwarg(self):
        SP=12
        KWRAMP=20
        KWSTEP=3
        KWDWELL=5
        config = static.get_config()  
        bb=config.get("heater")           
        val = bb.read()
        print "Ramping from %s to %s" % (val,SP)
        bb.ramp(SP,ramp=KWRAMP,step=KWSTEP,dwell=KWDWELL)
        print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
        bb.wait()
        myval = bb.read()
        print "%s rounded to %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),SP,places=1)
        print "check ramp value by kwargs"
        myramp = bb.ramprate()
        self.assertEqual(myramp,KWRAMP)
        mystep = bb.step()
        self.assertEqual(mystep,KWSTEP)
        mydwell = bb.dwell()
        self.assertEqual(mydwell,KWDWELL)

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

    def test_output_ramp_abort(self):
        SP=18
        config = static.get_config()  
        bb=config.get("heater")           
        val = bb.read()
        print "Ramping (then aborting) from %s to %s" % (val,SP)
        bb.ramp(SP)
        #gevent.sleep(3)
        #time.sleep(3)
        print ("Aborting")
        bb.abort()
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
