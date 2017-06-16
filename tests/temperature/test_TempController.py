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

def test_read_input(temp_tin):       
    print "%s" % (temp_tin.read())            

def test_input_state(temp_tin):
    temp_tin.state() 

def tests_output_state(temp_tout):
    temp_tout.state() 

def tests_output_limits(temp_tout):
    assert 10 == temp_tout.limits[0]

