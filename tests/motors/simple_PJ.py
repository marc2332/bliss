#!/usr/bin/python
# Very simple python program using EMotion.

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
            "..")))

import bliss

xml_config = """
<config>
    <!--<controller class="mockup"> -->  
    <controller class="PI_E712">
        <host value="id31pie712a" />
        <axis name="e712">
            <channel value="1" />
            <paranoia_mode value = "1" />
            <!-- <velocity value="100"/>  only needed for mockup-->
        </axis>
    </controller>
    <!--controller class="mockup">--> 
    <controller class="IcePAP">
        <host value="iceilab"/>
        <!--<libdebug value="1"/>-->
        <axis name="ujackpz">
            <address        value="08"/>
            <steps_per_unit value="100"/> <!-- 100 steps for 1 um-->
<!--            <backlash       value="0.01"/>
            <velocity       value="2500"/>-->
        </axis>
    </controller>
    <controller class="PiezoJack">
        <!-- value to which the piezo is set after icepap move-->
        <SetPiezo      value="7.5"/>
        <!-- The band in which the piezo alone moves
             e.g. value=11 => from 2 to 13 -->
        <PiezoLength   value="15"/>
        <PiezoBand     value="11"/>
        <factor        value="1.759"/>
        <offset        value="249.4"/>
        <axis name="bender" />
        <axis name="e712"    tags="piezo" />
        <axis name="ujackpz" tags="icepap" />
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
print "position:", my_axis.position()

# print "measured position:", my_axis.measured_position()
# print "getinfo:", my_axis.GetInfo()


# print "selftest:"
# my_axis.selftest()
print "getinfo :"
my_axis.GetInfo()

sys.exit()
