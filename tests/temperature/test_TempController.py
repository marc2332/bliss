# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

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
.yml file used for test:
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

def test_read_input(temp_tin):       
    print "%s" % (temp_tin.read())            

def test_input_state(temp_tin):
    temp_tin.state() 

def test_output_state(temp_tout):
    temp_tout.state() 

def test_output_limits(temp_tout):
    assert 10 == temp_tout.limits[0]

def test_output_deadband(temp_tout):
    assert 0.1 == temp_tout.deadband

def test_read_output(temp_tout):       
    print "%s" % (temp_tout.read())   

def test_read_input_from_loop(temp_tloop):       
    print "%s" % (temp_tloop.input.read())   

def test_read_output_from_loop(temp_tloop):       
    print "%s" % (temp_tloop.output.read())  

def test_set_ramprate(temp_tout):
    SP=45
    temp_tout.ramprate(SP)
    val = temp_tout.ramprate()                  
    assert SP == val
         
def test_set_stepval(temp_tout):
    SP=23
    temp_tout.step(SP)
    val = temp_tout.step()                  
    assert SP == val
         
def test_set_dwell(temp_tout):
    SP=12
    temp_tout.dwell(SP)
    val = temp_tout.dwell()                  
    assert SP == val 

def test_output_set(temp_tout):
    SP=10
    val = temp_tout.read()
    print "Direct setpoint from %s to %s" % (val,SP)
    temp_tout.set(SP)
    temp_tout.wait()
    myval = temp_tout.read()
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert  abs(SP-myround)<0.1 

def test_output_set_with_kwarg(temp_tout):
    SP=11
    KW=23
    val = temp_tout.read()
    print "Direct setpoint from %s to %s" % (val,SP)
    temp_tout.set(SP, step=KW)
    temp_tout.wait()
    myval = temp_tout.read()
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert abs(SP-myround)<0.1
    myset = temp_tout.set()
    myroundset = int(round(myset))
    assert abs(SP-myroundset)<0.1
    myval = temp_tout.step()
    assert myval == KW

        
def test_loop_set(temp_tloop):
    SP=18
    val = temp_tloop.output.read()
    print "Direct setpoint from %s to %s" % (val,SP)
    temp_tloop.set(SP)
    temp_tloop.output.wait()
    myval = temp_tloop.output.read()
    print myval
    myround = int(round(myval))
    print "%s rounded to %s" % (myval,myround)            
    assert abs(SP-myround)<0.1


def test_loop_regulation(temp_tloop):
    print "starting regulation"
    temp_tloop.on()
    print "Stopping regulation"
    temp_tloop.off()

def test_kp(temp_tloop):
    KW=13
    print "Setting P to %f" % KW
    temp_tloop.kp(KW)
    myval = temp_tloop.kp()
    assert KW == myval
        
def test_ki(temp_tloop):
    KW=50
    print "Setting I to %f" % KW
    temp_tloop.ki(KW)
    myval = temp_tloop.ki()
    assert KW == myval
        
def test_kd(temp_tloop):
    KW=1
    print "Setting D to %f" % KW
    temp_tloop.kd(KW)
    myval = temp_tloop.kd()
    assert KW == myval
        
def test_read_input_counter(temp_tin):       
    myval = temp_tin.read()
    print "%s" % (myval) 
    myvalcount = temp_tin.counter.read()
    assert abs(myval-myvalcount)<0.1

def test_read_output_counter(temp_tout):       
    myval = temp_tout.read()
    print "%s" % (myval) 
    myvalcount = temp_tout.counter.read()
    assert abs(myval-myvalcount)<0.1
           
