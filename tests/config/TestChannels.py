import os
import unittest
import sys
import gc

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..","..")))
os.environ["PYTHONPATH"]=":".join(sys.path)

import time
import multiprocessing
from bliss.config import channels
import subprocess

def test_ext_channel(keep_alive_delay, *args, **kwargs):
    kwargs = ["=".join([kwarg, str(value)]) for kwarg, value in kwargs.iteritems()]
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "test_channel.py"), str(keep_alive_delay)]+list(args)+kwargs
    #print cmd
    return subprocess.Popen(cmd, env=os.environ, stderr=subprocess.PIPE)

class TestBeacon(unittest.TestCase):
    def testNotInitialized(self):
        c = channels.Channel("test")
        self.assertEquals(c.value, channels.NotInitialized())

    def testSetChannel(self):
        c = channels.Channel("test", "test")
        self.assertEquals(c.value, 'test')

    def testExtChannel(self):
        p1 = test_ext_channel(2, "test", "hello")
        time.sleep(1) # wait for process to be started
        c = channels.Channel("test")
        p1_output = p1.stderr.readline().split('\n')[0]
        self.assertEquals(c.value, p1_output, 'hello')
        c.value = 5
        p1_output = p1.stderr.readline().split('\n')[0]
        self.assertEquals(p1_output, '5')
        p1.wait()
        
    def testTimeout(self):
        t0 = time.time()
        c = channels.Channel("test", timeout=0)
        self.assertTrue(time.time()-t0 < 0.02)
        t0 = time.time()
        c = channels.Channel("test", timeout=2)
        self.assertTrue(time.time()-t0 >= 2)
        self.assertEquals(c.value, channels.NotInitialized())


if __name__ == '__main__':
    unittest.main()
