import unittest
import sys
import os
import optparse
import re
import signal
import pdb


"""
Bliss generic library
"""
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))

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
            <velocity       value="2500"/>
        </axis>
    </controller>
    <group name="eh1">
        <axis name="mymot"/>
    </group>
</config>
"""


"""
Global resources, yes, I know it's bad
"""
hostname = ""
address = ""


"""
"""


def signal_handler(signal, frame):
    print "\nAbort request taken into account\n"
    finalize()
    sys.exit(-1)


def finalize():
    mymot = bliss.get_axis("mymot")
    mymot.controller.finalize()


"""
UnitTest list of tests
"""


class TestIcePAPController(unittest.TestCase):
    global hostname
    global address

    # called for each test
    def setUp(self):
        bliss.load_cfg_fromstring(config_xml % (hostname, address))

    # called at the end of each individual test
    def tearDown(self):
        pass

    def test_axis_creation(self):
        mymot = bliss.get_axis("mymot")
        self.assertTrue(mymot)

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

    def test_group_creation(self):
        mygrp = bliss.get_group("eh1")
        self.assertTrue(mygrp)

    def test_group_get_position(self):
        mygrp = bliss.get_group("eh1")
        #mymot.controller.log_level(3)
        pos_list = mygrp.position()
        #mymot.controller.log_level(3)
        for axis in pos_list:
            self.assertEqual(axis.position(), pos_list[axis])

    def test_group_move(self):
        mygrp = bliss.get_group("eh1")
        mymot = bliss.get_axis("mymot")
        pos_list = mygrp.position()
        pos_list[mymot] += 0.1
        mygrp.move(pos_list) # waits for the end of motions
        self.assertEqual(mygrp.state(), "READY")

    def test_group_stop(self):
        mygrp = bliss.get_group("eh1")
        mymot = bliss.get_axis("mymot")
        pos_list = mygrp.position()
        pos_list[mymot] -= 0.1
        mymot.controller.log_level(bliss.common.log.INFO)
        mygrp.move(pos_list, wait=False) 
        mygrp.stop() # waits for the end of motions
        mymot.controller.log_level(bliss.common.log.ERROR)
        self.assertEqual(mygrp.state(), "READY")


"""
Main entry point
"""
if __name__ == '__main__':

    # Get arguments
    usage = "Usage: %prog hostname motor_address"
    parser = optparse.OptionParser(usage)
    argv = sys.argv
    (settings, args) = parser.parse_args(argv)

    # Minimum check on arguements
    if len(args) <= 2:
        parser.error("Missing mandatory IcePAP hostname and motor address")
        sys.exit(-1)

    # Mandatory argument is the IcePAP hostname
    hostname = args[1]
    address  = args[2]

    # Avoid interaction of our arguments with unittest class
    del sys.argv[1:]

    # Intercept the <ctrl-c> to get out of infinite loops
    signal.signal(signal.SIGINT, signal_handler)

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
    suite = loader.loadTestsFromTestCase(TestIcePAPController)
    unittest.TextTestRunner(verbosity=3).run(suite)

    # normal end
    finalize()
