#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''
Very simple python program using EMotion.
'''

import os
import sys

__author__ = 'Holger Witsch'
__version__ = ''


displacement = 10
try:
    displacement = int(sys.argv[1])
except :
    print "no argument as displacement"
else:
    print displacement, "****************"

# os.path.join(os.environ["HOME"], "bliss")

EMOTION_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

sys.path.insert(0, EMOTION_PATH)
sys.path.insert(0, os.path.join(EMOTION_PATH, "tango"))
sys.path.insert(1, "/bliss/users/blissadm/python/bliss_modules/debian6")
sys.path.insert(1, "/bliss/users/blissadm/python/bliss_modules")


sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss

xml_config = """
<config>

    <controller class="PI_E712">
        <host value="id31pie712a" />
<!--
        <encoder name="e712enc">
          <steps_per_unit value="1"/>
          <tolerance value="0.001"/>
        </encoder>
        <axis name="e712" encoder="e712enc">
-->
        <axis name="e712">
        <channel value="1" />
        <paranoia_mode value="0" />

       <settings><dial_position value="9.49507999" /><position value="9.49507999" /><velocity value="2500.0" /></settings>
       </axis>
    </controller>

    <controller class="IcePAP">
        <host value="iceilab" />

        <axis name="icepap">
            <address value="08" />
            <steps_per_unit value="100" />
            <backlash value="15" />
            <high_limit value="1000000000.0" />
            <low_limit value="-70" />
        <settings><velocity value="40.0" /><dial_position value="30.9" /><position value="30.9" /><high_limit value="1000000000.0" /><low_limit value="-70.0" /></settings></axis>
    </controller>
    <controller class="PiezoJack">

        <PiezoLength value="15" />
        <SetPiezo value="7.5" />

        <PiezoBand value="11" />

        <axis name="bender"><settings><velocity value="40.0" /><dial_position value="26.7984104203" /><position value="26.7984104203" /></settings></axis>
        <axis name="e712" tags="piezo" />
        <axis name="icepap" tags="icepap" />
    </controller>
</config>
"""

bliss.load_cfg_fromstring(xml_config)

bliss.common.log.level(bliss.log.DEBUG)


my_axis = bliss.get_axis("bender")

x = my_axis.position()
print "position:", x
print "state   :", my_axis.state()

how_much = displacement
# if x > 600:
    # how_much = -how_much

print "relative move by :", how_much

raw_input('Press enter to continue: ')

my_axis.rmove(how_much)

new_pos = my_axis.position()
print "position:", new_pos


if abs(x - new_pos) < .5:
    print """
It is likely that your movement hasn't worked, because the PiezoJack.py method _do_move
is still a greenlet, as it should be for the use as device server. However simple_PJ.py
doesn't work as such. One needs to comment out the @task around line 244.
"""

# print "measured position:", my_axis.measured_position()
# print "getinfo:", my_axis.GetInfo()


# print "selftest:"
# my_axis.selftest()

sys.exit()
