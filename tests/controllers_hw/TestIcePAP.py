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
        os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
    ),
)

import bliss
from bliss.config.motors import load_cfg_fromstring, get_axis, get_encoder
from bliss.common.motor_group import Group


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

        <axis name="mymot1">
            <address        value="%s"/>
            <steps_per_unit value="2000"/>
            <backlash       value="0.01"/>
            <velocity       value="2"/>    // unit is unit/sec
            <acceleration   value="10"/>   // unit is unit/sec2
        </axis>

        <axis name="mymot2">
            <address        value="%s"/>
            <steps_per_unit value="2000"/>
            <backlash       value="0.01"/>
            <velocity       value="2.5"/>  // unit is unit/sec
            <acceleration   value="10"/>   // unit is unit/sec2
        </axis>

        <encoder name="myenc">
            <address        value="%s"/>
            <type           value="encin"/> // optional
            <steps_per_unit value="1000"/>
        </encoder>

    </controller>
</config>
"""


"""
Global resources, yes, I know it's bad
"""
hostname = ""
address = ""
address2 = ""

"""
"""


# def signal_handler(signal, frame):
def signal_handler(*args):
    print("\nAbort request taken into account\n")
    finalize()

    # needed to stop unittest sequence of tests
    # raise KeyboardInterrupt()


def finalize():

    mymot1 = get_axis("mymot1")
    mymot1.stop()
    mymot2 = get_axis("mymot2")
    mymot2.stop()

    # needed to stop threads of Deep module
    # mymot1.controller.log_level(bliss.common.log.INFO)
    mymot1.controller.finalize()


"""
UnitTest list of tests
"""


class TestIcePAPController(unittest.TestCase):
    global hostname
    global address
    global address2

    # called for each test
    def setUp(self):
        load_cfg_fromstring(config_xml % (hostname, address, address2, address))

    # called at the end of each individual test
    def tearDown(self):
        pass

    def test_axis_creation(self):
        mymot1 = get_axis("mymot1")
        self.assertTrue(mymot1)

    """
    def test_ctrlc(self):
        mymot1 = get_axis("mymot1")
        move_greenlet = mymot1.rmove(1000, wait=False)
        self.assertEqual(mymot1.state(), "MOVING")
        gevent.sleep(0.1)
        move_greenlet.kill(KeyboardInterrupt)
        gevent.sleep(0.2)
        self.assertEqual(mymot1.state(), "READY")
    """

    """
    def test_group_ctrlc(self):
        mygrp  = bliss.get_group("eh1")
        mymot1 = get_axis("mymot1")
        mymot2 = get_axis("mymot2")
        #mymot1.controller.log_level(bliss.common.log.INFO)
        for i in range(10):
            move_greenlet = mygrp.rmove(mymot1, 1000, mymot2,1000, wait=False)
            self.assertEqual(mygrp.state(), "MOVING")
            gevent.sleep(0.1)
            move_greenlet.kill(KeyboardInterrupt)
            gevent.sleep(0.5)
            self.assertEqual(mymot1.state(), "READY")
            self.assertEqual(mymot2.state(), "READY")
            self.assertEqual(mygrp.state(), "READY")
        #mymot1.controller.log_level(bliss.common.log.ERROR)
    """

    def test_axis_get_position(self):
        mymot1 = get_axis("mymot1")
        pos = mymot1.position()

    def test_axis_set_position(self):
        mymot1 = get_axis("mymot1")
        pos = 2.0  # given in mm
        self.assertEqual(mymot1.position(pos), pos)

    def test_axis_get_id(self):
        mymot1 = get_axis("mymot1")
        self.assertTrue(
            re.match(r"[a-f0-9A-F]{4}.[a-f0-9A-F]{4}.[a-f0-9A-F]{4}", mymot1.get_id())
        )

    def test_axis_get_velocity(self):
        mymot1 = get_axis("mymot1")
        vel = mymot1.velocity()

    def test_axis_set_velocity(self):
        mymot1 = get_axis("mymot1")
        vel = 5
        mymot1.velocity(vel)
        self.assertEqual(mymot1.velocity(), vel)

    def test_axis_set_velocity_error(self):
        mymot1 = get_axis("mymot1")
        vel = 5000
        self.assertRaises(Exception, mymot1.velocity, vel)

    def test_axis_get_acctime(self):
        mymot1 = get_axis("mymot1")
        acc = mymot1.acctime()

    def test_axis_set_acctime(self):
        mymot1 = get_axis("mymot1")
        acc = 0.250
        self.assertEqual(mymot1.acctime(acc), acc)

    def test_axis_state(self):
        mymot1 = get_axis("mymot1")
        mymot1.state()

    def test_axis_stop(self):
        mymot1 = get_axis("mymot1")
        mymot1.stop()

    def test_axis_move(self):
        mymot1 = get_axis("mymot1")
        pos = mymot1.position()
        mymot1.move(pos + 0.1)  # waits for the end of motion

    def test_axis_move_backlash(self):
        mymot1 = get_axis("mymot1")
        pos = mymot1.position()
        mymot1.move(pos - 0.1)

    def test_axis_rmove(self):
        mymot1 = get_axis("mymot1")
        mymot1.rmove(0.1)

    def test_axis_home_search(self):
        # launch a never ending motion as there is no home signal.
        # WARINING: check with icepapcms that the concerned axis an home
        # signal configured (for instance "Lim+") because the default
        # icepapcms configuration is "None" which will make the test fails.
        mymot1 = get_axis("mymot1")
        mymot1.home(wait=False)

        # give time to motor to start
        gevent.sleep(0.1)
        self.assertEqual(mymot1.state(), "MOVING")

        # stop the never ending motion
        mymot1.stop()

        # wait for the motor stop
        while mymot1.state() == "MOVING":
            gevent.sleep(0.1)

    def test_axis_limit_search(self):
        mymot1 = get_axis("mymot1")
        # test both search senses
        for sense in [-1, 1]:

            # launch a never ending motion as there is no limitswitch
            mymot1.hw_limit(sense, wait=False)

            # give time to motor to start
            gevent.sleep(0.1)
            self.assertEqual(mymot1.state(), "MOVING")

            # stop the never ending motion
            mymot1.stop()

            # wait for the motor stop
            while mymot1.state() == "MOVING":
                gevent.sleep(0.1)

    def test_group_creation(self):
        # group creation
        mymot1 = get_axis("mymot1")
        mymot2 = get_axis("mymot2")
        mygrp = Group(mymot1, mymot2)

        self.assertTrue(mygrp)

    def test_group_get_position(self):
        # group creation
        mymot1 = get_axis("mymot1")
        mymot2 = get_axis("mymot2")
        mygrp = Group(mymot1, mymot2)

        # mymot1.controller.log_level(3)
        pos_list = mygrp.position()
        # mymot1.controller.log_level(3)
        for axis in pos_list:
            self.assertEqual(axis.position(), pos_list[axis])

    def test_group_move(self):
        # group creation
        mymot1 = get_axis("mymot1")
        mymot2 = get_axis("mymot2")
        mygrp = Group(mymot1, mymot2)

        pos_list = mygrp.position()
        pos_list[mymot1] += 0.1

        # waits for the end of motions
        mygrp.move(pos_list)
        self.assertEqual(mygrp.state(), "READY")

    def test_group_stop(self):
        # group creation
        mymot1 = get_axis("mymot1")
        mymot2 = get_axis("mymot2")
        mygrp = Group(mymot1, mymot2)

        pos_list = mygrp.position()
        pos_list[mymot1] -= 0.1

        # non blocking call
        mygrp.move(pos_list, wait=False)

        # waits for the end of motions
        mygrp.stop()
        self.assertEqual(mygrp.state(), "READY")

    def test_encoder_creation(self):
        myenc = get_encoder("myenc")
        self.assertTrue(myenc)

    def test_encoder_get_position(self):
        myenc = get_encoder("myenc")
        # myenc.controller.log_level(bliss.common.log.INFO)
        pos = myenc.read()
        # myenc.controller.log_level(bliss.common.log.ERROR)

    def test_encoder_set_position(self):
        myenc = get_encoder("myenc")
        pos = 2.0  # given in mm
        self.assertEqual(myenc.set(pos), pos)

    def test_mulitple_moves(self):
        mymot1 = get_axis("mymot1")
        mymot2 = get_axis("mymot2")

        def task_cyclic(mot):
            while True:
                mot.position()
                gevent.sleep(0.1)

        # mymot1.controller.log_level(bliss.common.log.INFO)

        # launch several greenlets
        mymot1.move(mymot1.position() + 1000, wait=False)
        gevent.sleep(0.1)
        mymot2.move(mymot2.position() - 1000, wait=False)

        task = gevent.spawn(task_cyclic, mymot2)
        for i in range(10):
            mymot1.position()
            mymot2.position()

        mymot1.stop()
        self.assertEqual(mymot1.state(), "READY")
        mymot1.move(mymot1.position() - 1000, wait=False)
        for i in range(10):
            mymot1.position()
            mymot2.position()
            gevent.sleep(0.1)

        mymot1.stop()
        mymot2.stop()
        self.assertEqual(mymot1.state(), "READY")
        self.assertEqual(mymot2.state(), "READY")

        # mymot1.controller.log_level(bliss.common.log.ERROR)

        task.kill()
        task.join()


"""
Main entry point
"""
if __name__ == "__main__":

    # Get arguments
    usage = "Usage  : %prog hostname motor_address motor_address\n"
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
    address = args[2]
    address2 = args[3]

    # Avoid interaction of our arguments with unittest class
    del sys.argv[1:]

    # Intercept the <ctrl-c> to get out of infinite loops
    gevent.signal(signal.SIGINT, signal_handler)

    # Launch the tests sequence
    print('\nTesting IcePAP control on system "%s"\n' % hostname)
    print("\n".rjust(70, "-"))

    # Change the default unittest test sequence order from cmp() to line number
    loader = unittest.TestLoader()
    ln = lambda f: getattr(TestIcePAPController, f).__func__.__code__.co_firstlineno
    lncmp = lambda a, b: cmp(ln(a), ln(b))
    loader.sortTestMethodsUsing = lncmp

    # NOTE: unittest.main(verbosity=2) not supported under Python 2.6
    suite = loader.loadTestsFromTestCase(TestIcePAPController)
    unittest.TextTestRunner(verbosity=3).run(suite)

    # normal end
    finalize()
