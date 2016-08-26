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


"""
IcePAP specific library
"""
"""
sys.path.insert(
    0,
    os.path.abspath("/segfs/bliss/source/hardware/IcePAP/client/python/"))
"""


"""
Example of Bliss configuration
"""
config_xml = """
<config>
    <controller class="IcePAP" name="test">

        <host value="%s"/>
        <libdebug value="1"/>

        <axis name="mymot">
            <address        value="%s"/>
            <steps_per_unit value="2000"/>
            <backlash       value="0.01"/>
            <velocity       value="2500"/>   // unit is mm/sec
            <acceleration   value="10"/>   // unit is mm/sec
        </axis>

        <axis name="mymot2">
            <address        value="%s"/>
            <steps_per_unit value="2000"/>
            <backlash       value="0.01"/>
            <velocity       value="2500"/>   // unit is mm/sec
            <acceleration   value="10"/>   // unit is mm/sec
        </axis>

        <encoder name="myenc">
            <address        value="%s"/>
            <type           value="encin"/>  // optional
            <steps_per_unit value="1000"/>
        </encoder>

    </controller>
</config>
"""


"""
Global resources, yes, I know it's bad
"""
hostname = ""
address  = ""
address2 = ""

"""
"""


#def signal_handler(signal, frame):
def signal_handler(*args):
    print "\nAbort request taken into account\n"
    finalize()

    # needed to stop unittest sequence of tests
    #raise KeyboardInterrupt()


def finalize():
    mymot = bliss.get_axis("mymot")
    #mymot.controller.log_level(bliss.common.log.INFO)

    # needed to stop threads of Deep module
    mymot.controller.finalize()



"""
UnitTest list of tests
"""


class TestIcePAPController(unittest.TestCase):
    global hostname
    global address
    global address2

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml % 
            (hostname, address, address2, address))

    # called at the end of each individual test
    def tearDown(self):
        pass

    def test_axis_creation(self):
        mymot = bliss.get_axis("mymot")
        self.assertTrue(mymot)

    """
    def test_ctrlc(self):
        mymot = bliss.get_axis("mymot")
        move_greenlet = mymot.rmove(1000, wait=False)
        self.assertEqual(mymot.state(), "MOVING")
        gevent.sleep(0.1)
        move_greenlet.kill(KeyboardInterrupt)
        gevent.sleep(0.2)
        self.assertEqual(mymot.state(), "READY")
    """

    """
    def test_group_ctrlc(self):
        mygrp = bliss.get_group("eh1")
        mymot = bliss.get_axis("mymot")
        mymot2= bliss.get_axis("mymot2")
        #mymot.controller.log_level(bliss.common.log.INFO)
        for i in range(10):
            move_greenlet = mygrp.rmove(mymot, 1000, mymot2,1000, wait=False)
            self.assertEqual(mygrp.state(), "MOVING")
            gevent.sleep(0.1)
            move_greenlet.kill(KeyboardInterrupt)
            gevent.sleep(0.5)
            self.assertEqual(mymot.state(), "READY")
            self.assertEqual(mymot2.state(), "READY")
            self.assertEqual(mygrp.state(), "READY")
        #mymot.controller.log_level(bliss.common.log.ERROR)
    """

    def test_axis_get_position(self):
        mymot = bliss.get_axis("mymot")
        pos = mymot.position()

    def test_axis_set_position(self):
        mymot = bliss.get_axis("mymot")
        pos = 2.0  # given in mm
        self.assertEqual(mymot.position(pos), pos)

    def test_axis_get_id(self):
        mymot = bliss.get_axis("mymot")
        self.assertTrue(
            re.match(
                r"[a-f0-9A-F]{4}.[a-f0-9A-F]{4}.[a-f0-9A-F]{4}",
                mymot.get_identifier()))

    def test_axis_get_velocity(self):
        mymot = bliss.get_axis("mymot")
        vel = mymot.velocity()

    def test_axis_set_velocity(self):
        mymot = bliss.get_axis("mymot")
        vel = 5000
        self.assertEqual(mymot.velocity(vel), vel)

    def test_axis_get_acctime(self):
        mymot = bliss.get_axis("mymot")
        acc = mymot.acctime()

    def test_axis_set_acctime(self):
        mymot = bliss.get_axis("mymot")
        acc = 0.250
        self.assertEqual(mymot.acctime(acc), acc)

    def test_axis_state(self):
        mymot = bliss.get_axis("mymot")
        mymot.state()

    def test_axis_stop(self):
        mymot = bliss.get_axis("mymot")
        mymot.stop()

    def test_axis_move(self):
        mymot = bliss.get_axis("mymot")
        pos = mymot.position()
        mymot.move(pos + 0.1) # waits for the end of motion

    def test_axis_move_backlash(self):
        mymot = bliss.get_axis("mymot")
        pos = mymot.position()
        mymot.move(pos - 0.1)

    def test_axis_rmove(self):
        mymot = bliss.get_axis("mymot")
        mymot.rmove(0.1)

    def test_axis_home_search(self):
        # launch a never ending motion as there is no home signal
        mymot = bliss.get_axis("mymot")
        mymot.home(wait=False)

        # give time to motor to start
        gevent.sleep(0.1)
        self.assertEqual(mymot.state(), 'MOVING')

        # stop the never ending motion
        mymot.stop()

        # wait for the motor stop
        while mymot.state() == 'MOVING':
            gevent.sleep(0.1)

    def test_axis_limit_search(self):
        mymot = bliss.get_axis("mymot")
        # test both search senses
        for sense in [-1, 1]:

            # launch a never ending motion as there is no limitswitch 
            mymot.hw_limit(sense, wait=False)

            # give time to motor to start
            gevent.sleep(0.1)
            self.assertEqual(mymot.state(), 'MOVING')
    
            # stop the never ending motion
            mymot.stop()

            # wait for the motor stop
            while mymot.state() == 'MOVING':
                gevent.sleep(0.1)

    def test_group_creation(self):
        # group creation
        mymot = bliss.get_axis("mymot")
        mymot2= bliss.get_axis("mymot2")
        mygrp = bliss.Group(mymot, mymot2)

        self.assertTrue(mygrp)

    def test_group_get_position(self):
        # group creation
        mymot = bliss.get_axis("mymot")
        mymot2= bliss.get_axis("mymot2")
        mygrp = bliss.Group(mymot, mymot2)

        #mymot.controller.log_level(3)
        pos_list = mygrp.position()
        #mymot.controller.log_level(3)
        for axis in pos_list:
            self.assertEqual(axis.position(), pos_list[axis])

    def test_group_move(self):
        # group creation
        mymot = bliss.get_axis("mymot")
        mymot2= bliss.get_axis("mymot2")
        mygrp = bliss.Group(mymot, mymot2)

        pos_list = mygrp.position()
        pos_list[mymot] += 0.1

        # waits for the end of motions
        mygrp.move(pos_list) 
        self.assertEqual(mygrp.state(), "READY")

    def test_group_stop(self):
        # group creation
        mymot = bliss.get_axis("mymot")
        mymot2= bliss.get_axis("mymot2")
        mygrp = bliss.Group(mymot, mymot2)

        pos_list = mygrp.position()
        pos_list[mymot] -= 0.1

        # non blocking call
        mygrp.move(pos_list, wait=False) 

        # waits for the end of motions
        mygrp.stop() 
        self.assertEqual(mygrp.state(), "READY")

    def test_encoder_creation(self):
        myenc = bliss.get_encoder("myenc")
        self.assertTrue(myenc)

    def test_encoder_get_position(self):
        myenc = bliss.get_encoder("myenc")
        #myenc.controller.log_level(bliss.common.log.INFO)
        pos = myenc.read()
        #myenc.controller.log_level(bliss.common.log.ERROR)

    def test_encoder_set_position(self):
        myenc = bliss.get_encoder("myenc")
        pos = 2.0  # given in mm
        self.assertEqual(myenc.set(pos), pos)

"""
Main entry point
"""
if __name__ == '__main__':

    # Get arguments
    usage  = "Usage  : %prog hostname motor_address motor_address\n"
    usage += "Example: python %prog iceeu2 2 3"
    parser = optparse.OptionParser(usage)
    argv = sys.argv
    (settings, args) = parser.parse_args(argv)

    # Minimum check on arguements
    if len(args) <= 3:
        parser.error("Missing mandatory IcePAP hostname and motor address")
        sys.exit(-1)

    # Mandatory argument is the IcePAP hostname
    hostname = args[1]
    address  = args[2]
    address2 = args[3]

    # Avoid interaction of our arguments with unittest class
    del sys.argv[1:]

    # Intercept the <ctrl-c> to get out of infinite loops
    gevent.signal(signal.SIGINT, signal_handler)

    # Launch the tests sequence
    print "\nTesting IcePAP control on system \"%s\"\n" % hostname
    print "\n".rjust(70, "-")

    # Change the default unittest test sequence order from cmp() to line number
    loader = unittest.TestLoader()
    ln = lambda f: getattr(TestIcePAPController, f).\
        im_func.func_code.co_firstlineno
    lncmp = lambda a, b: cmp(ln(a), ln(b))
    loader.sortTestMethodsUsing = lncmp

    # NOTE: unittest.main(verbosity=2) not supported under Python 2.6
    suite  = loader.loadTestsFromTestCase(TestIcePAPController)
    unittest.TextTestRunner(verbosity=3).run(suite)

    # normal end
    finalize()
