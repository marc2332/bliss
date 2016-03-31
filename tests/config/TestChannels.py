import os
import unittest
import sys
import gc
import gevent
import signal

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
    return subprocess.Popen(cmd, env=os.environ, stderr=subprocess.PIPE)

class TestBeacon(unittest.TestCase):
    def testNotInitialized(self):
        c = channels.Channel("test")
        self.assertEquals(c.value, None)

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
        gevent.sleep(0.1)
        p1_output = p1.stderr.readline().split('\n')[0]
        self.assertEquals(p1_output, '5')
        p1.wait()

    def testTimeout(self):
        p = test_ext_channel(10, "test2", "hello")
        time.sleep(1)
        os.kill(p.pid, signal.SIGSTOP)
        c = channels.Channel("test2")
        self.assertEquals(c.timeout, 3)
        c.timeout = 1
        def get_value(c):
            return c.value
        t0 = time.time()
        self.assertRaises(RuntimeError,get_value,c)
        self.assertTrue(time.time()-t0 >= 1)
        os.kill(p.pid, signal.SIGCONT)
        self.assertEquals(c.value, "hello")

if __name__ == '__main__':
    unittest.main()
