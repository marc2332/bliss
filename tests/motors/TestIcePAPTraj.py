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
            <steps_per_unit value="200"/>
            <backlash       value="0.01"/>
            <velocity       value="20"/>  // unit is mm/sec
            <accleration    value="80"/>  // unit is mm/sec2
            <encoder_steps_per_unit value="1000"/>
        </axis>
        <axis name="mymot2">
            <address        value="%s"/>
            <steps_per_unit value="200"/>
            <backlash       value="0.01"/>
            <velocity       value="20"/>   // unit is mm/sec
            <acceleration   value="80"/>   // unit is mm/sec2
        </axis>
    </controller>

    <controller class="IcePAPTraj" name="mytraj">
        <axis name="mypar">
            <axislist       value="mymot mymot2"/>
            <velocity       value="1"/>    // unit is par/sec
        </axis>
    </controller>
</config>
"""


"""
            <acceleration   value="4"/>    // unit is par/sec2
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
        bliss.load_cfg_fromstring(config_xml % (hostname, address, address2))

    # called at the end of each individual test
    def tearDown(self):
        pass

    # as the test are ordered, this method will be executed first
    def test_hardware_axes_preparation(self):

        # If motors are moving, the power can not be switched on
        # therefore hide exception
        mymot  = bliss.get_axis("mymot")
        mymot2 = bliss.get_axis("mymot2")
        #mymot.controller.log_level(bliss.common.log.INFO)
        mymot.controller.stop(mymot)
        mymot2.controller.stop(mymot2)
        #mymot.controller.log_level(bliss.common.log.ERROR)

        # NOTE MP: 2015Mar17: the current eMotion doesn't call the
        # controller stop() if it doesn't know that a motion is taking
        # place on the hardware. Therefore bypass eMotion
        while mymot.state() == 'MOVING':
            gevent.sleep(0.1)
        while mymot2.state() == 'MOVING':
            gevent.sleep(0.1)

        # the IcePAP will move, therefore put it close to the
        # target position to avoid long wait
        mymot.dial(0)
        mymot.position(0)
        mymot2.dial(0)
        mymot2.position(0)

    def test_axis_creation(self):
        mypar = bliss.get_axis("mypar")
        self.assertTrue(mypar)


    def test_set_parameter(self):
        mypar = bliss.get_axis("mypar")
        par_list = range(100)
        mypar.set_parameter(par_list)
        self.assertEqual(mypar.get_parameter(), par_list)

    def test_drain_trajectory(self):
        mypar = bliss.get_axis("mypar")
        par_list = range(100)
        mypar.set_parameter(par_list)
        mypar.drain()
        self.assertEqual(len(mypar.get_parameter()), 0)

    def test_set_parameter_nonempty(self):
        mypar = bliss.get_axis("mypar")
        par_list = range(100)
        mypar.set_parameter(par_list)
        self.assertRaises(ValueError, mypar.set_parameter, par_list)

    def test_set_trajectory(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(100)
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)

    def test_set_trajectory_wrongrange(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(10)
        mypar.set_parameter(par_list)
        self.assertRaises(ValueError, mypar.set_trajectory, mymot, pos_list)

    def test_set_trajectory_overwrite(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(100)
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)
        self.assertRaises(ValueError, mypar.set_trajectory, mymot, pos_list)
        
    def test_load_trajectory(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = [ x *10 for x in range(100) ]
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)
        mypar.load()

    def test_load_multi_axes_trajectory(self):
        mypar  = bliss.get_axis("mypar")
        mymot  = bliss.get_axis("mymot")
        mymot2 = bliss.get_axis("mymot2")

        par_list = range(100)
        mypar.set_parameter(par_list)

        pos_list = [ x *10 for x in range(100) ]
        mypar.set_trajectory(mymot,  pos_list)
        pos_list = [ x *20 for x in range(100) ]
        mypar.set_trajectory(mymot2, pos_list)

        mypar.load()

    def test_put_all_axes_on_trajectory(self):
        mypar  = bliss.get_axis("mypar")
        mymot  = bliss.get_axis("mymot")
        mymot2 = bliss.get_axis("mymot2")

        par_list = range(100)
        mypar.set_parameter(par_list)

        pos_list = [ x * 1.5 for x in range(100) ]
        mypar.set_trajectory(mymot,  pos_list)
        pos_list2 = [ x * 2 for x in range(100) ]
        mypar.set_trajectory(mymot2, pos_list2)

        mypar.load()

        # IcePAP motors will move, blocking call
        mypar.sync(1)

        self.assertEqual(mymot.position(),  pos_list[1])
        self.assertEqual(mymot2.position(), pos_list2[1])

    def test_get_parameter_velocity_empty(self):
        mypar = bliss.get_axis("mypar")
        vel = mypar.velocity()

    def test_get_parameter_velocity(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(100)
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)
        mypar.load()

        vel = mypar.velocity()

    def test_set_parameter_velocity_empty(self):
        mypar = bliss.get_axis("mypar")
        vel = 1
        self.assertEqual(mypar.velocity(vel), vel)

    def test_set_parameter_velocity(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(100)
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)
        mypar.load()

        vel = 1
        self.assertEqual(mypar.velocity(vel), vel)

    def test_get_parameter_acctime_empty(self):
        mypar = bliss.get_axis("mypar")
        vel = mypar.acctime()

    def test_get_parameter_acctime(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(100)
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)
        mypar.load()

        acc = mypar.acctime()

    def test_set_parameter_acctime_empty(self):
        mypar = bliss.get_axis("mypar")
        acc = 0.250
        self.assertEqual(mypar.acctime(acc), acc)

    def test_set_parameter_acctime(self):
        mypar = bliss.get_axis("mypar")
        mymot = bliss.get_axis("mymot")
        par_list = range(100)
        pos_list = range(100)
        mypar.set_parameter(par_list)
        mypar.set_trajectory(mymot, pos_list)
        mypar.load()

        acc = 0.250
        self.assertEqual(mypar.acctime(acc), acc)

    def test_move_all_axes_on_trajectory(self):
        mypar  = bliss.get_axis("mypar")
        mymot  = bliss.get_axis("mymot")
        mymot2 = bliss.get_axis("mymot2")

        par_list = range(100)
        mypar.set_parameter(par_list)

        pos_list = [ x * 1.5 for x in range(100) ]
        mypar.set_trajectory(mymot,  pos_list)
        pos_list2 = [ x * 2 for x in range(100) ]
        mypar.set_trajectory(mymot2, pos_list2)

        mypar.load()
        mypar.sync(1)

        # IcePAP motors will move, blocking call
        mypar.move(2)

        self.assertEqual(mymot.position(),  pos_list[2])
        self.assertEqual(mymot2.position(), pos_list2[2])

    def test_stop_move(self):
        mypar  = bliss.get_axis("mypar")
        mymot  = bliss.get_axis("mymot")
        mymot2 = bliss.get_axis("mymot2")

        par_list = range(100)
        mypar.set_parameter(par_list)

        pos_list = [ x * 1.5 for x in range(100) ]
        mypar.set_trajectory(mymot,  pos_list)
        pos_list2 = [ x * 2 for x in range(100) ]
        mypar.set_trajectory(mymot2, pos_list2)

        mypar.load()
        mypar.sync(1)

        mypar.move(2, wait=False)
        mypar.stop()


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
