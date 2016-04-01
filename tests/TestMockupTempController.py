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

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))
"""
"""
To work in my local dev
"""
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


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

    def test_creationinputs(self):
        config = static.get_config()     
        aa=config.get("thermo_sample")
        self.assertTrue(aa)

    def test_creationoutputs(self):
        config = static.get_config()     
        bb=config.get("heater")
        self.assertTrue(bb)


    def test_creationctrl_loops(self):       
        config = static.get_config()     
        cc=config.get("sample_regulation")
        self.assertTrue(cc)

    def test_read(self):       
        config = static.get_config()     
        aa=config.get("thermo_sample")
        bb=config.get("heater") 
        print "%s %s" % (aa.read(),bb.read())            


    def test_setpoint(self):
        config = static.get_config()  
        aa=config.get("thermo_sample")
        bb=config.get("heater")           
        cc=config.get("sample_regulation")
        bb.setpoint(10)
        print ("Wait for end of setpoint")
        bb.wait()
        myval = bb.read()
        print "%s %s" % (myval,int(round(myval)))            
        self.assertAlmostEqual(int(round(myval)),10,places=1)



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
