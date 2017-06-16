import pytest
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
Pytest list of tests
"""

def test_output_ramp(temp_tout):
    SP=13
    val = temp_tout.read()
    print "Ramping from %s to %s" % (val,SP)
    temp_tout.ramp(SP)
    print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
    temp_tout.wait()
    myval = temp_tout.read()
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert abs(myround-SP)<0.1

def test_output_ramp_with_kwarg(temp_tout):
    SP=12
    KWRAMP=20
    KWSTEP=3
    KWDWELL=5
    val = temp_tout.read()
    print "Ramping from %s to %s" % (val,SP)
    temp_tout.ramp(SP,ramp=KWRAMP,step=KWSTEP,dwell=KWDWELL)
    print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
    temp_tout.wait()
    myval = temp_tout.read()
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert abs(myround-SP)<0.1
    print "check ramp value by kwargs"
    myramp = temp_tout.ramprate()
    assert myramp == KWRAMP
    mystep = temp_tout.step()
    assert mystep == KWSTEP
    mydwell = temp_tout.dwell()
    assert mydwell == KWDWELL

def test_output_ramp_stop(temp_tout):
    SP=15
    val = temp_tout.read()
    print "Ramping (then stopping) from %s to %s" % (val,SP)
    temp_tout.ramp(SP)
    print ("Stopping")
    temp_tout.stop()
    myval = temp_tout.read()
    print "Now at: %s" % myval  

def test_output_ramp_abort(temp_tout):
    SP=18
    val = temp_tout.read()
    print "Ramping (then aborting) from %s to %s" % (val,SP)
    temp_tout.ramp(SP)
    print ("Aborting")
    temp_tout.abort()
    myval = temp_tout.read()
    print "Now at: %s" % myval  

def test_loop_output_ramp(temp_tloop):
    SP=20
    val = temp_tloop.output.read()
    print "Ramping from %s to %s" % (val,SP)
    temp_tloop.output.ramp(SP)
    print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
    temp_tloop.output.wait()
    myval = temp_tloop.output.read()
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert abs(myround-SP)<0.1

def test_loop_output_ramp_stop(temp_tloop):
    SP=20
    val = temp_tloop.output.read()
    print "Ramping (then stopping) from %s to %s" % (val,SP)
    temp_tloop.output.ramp(SP)
    gevent.sleep(3)
    print ("Stopping")
    temp_tloop.output.stop()
    myval = temp_tloop.output.read()
    print "Now at: %s" % myval  

def test_loop_ramp(temp_tloop):
    SP=15
    val = temp_tloop.output.read()
    print "Ramping from %s to %s" % (val,SP)
    temp_tloop.ramp(SP)
    print "Wait for end of setpoint (around %s seconds)" % (int(abs(SP-val))*2)
    temp_tloop.output.wait()
    myval = temp_tloop.output.read()
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert abs(myround-SP)<0.1

        

