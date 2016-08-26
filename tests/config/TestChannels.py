# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

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
            os.path.pardir, os.path.pardir)))
os.environ["PYTHONPATH"]=":".join(sys.path)

import time
from multiprocessing import Process,Queue,Pipe
from bliss.config import channels

def _ext_channel(keep_alive_delay,pipe,queue,*args,**kwargs):
    c = channels.Channel(*args,**kwargs)
    queue.put(c.value)
    pipe.send('|')
    gevent.sleep(keep_alive_delay)
    queue.put(c.value)

def test_ext_channel(keep_alive_delay, *args, **kwargs):
    r,w = Pipe(False)
    q = Queue()
    fun_args = [keep_alive_delay,w,q]
    fun_args.extend(args)
    p = Process(target=_ext_channel,args=fun_args,
                kwargs=kwargs)
    p.start()
    return p,r,q

class TestBeacon(unittest.TestCase):
    def setUp(self):
        time.sleep(0.1)

    def testNotInitialized(self):
        c = channels.Channel("tagada")
        self.assertEquals(c.value, None)

    def testSetChannel(self):
        c = channels.Channel("super mario", "test")
        self.assertEquals(c.value, 'test')

    def testExtChannel(self):
        p1,pipe,queue = test_ext_channel(4, "gerard", "hello")
        pipe.recv()
        c = channels.Channel("gerard")
        p1_output = queue.get()
        self.assertEquals(c.value, p1_output, 'hello')
        c.value = 5
        gevent.sleep(0.1)
        p1_output = queue.get()
        self.assertEquals(p1_output, 5)
        p1.join()

    def testTimeout(self):
        p,pipe,queue = test_ext_channel(3, "test2", "hello")
        pipe.recv()
        os.kill(p.pid, signal.SIGSTOP)
        c = channels.Channel("test2")
        self.assertEquals(c.timeout, 3)
        c.timeout = .5
        def get_value(c):
            return c.value
        t0 = time.time()
        self.assertRaises(RuntimeError,get_value,c)
        self.assertTrue(time.time()-t0 >= .5)
        os.kill(p.pid, signal.SIGCONT)
        self.assertEquals(c.value, "hello")
        p.join()

    def testCallback(self):
        p,pipe,queue = test_ext_channel(2, "bla", "hello")
        pipe.recv()
        received_value = {"value":None }
        cbk_event = gevent.event.Event()
        def cbk(value, received_value=received_value):
            cbk_event.set()
            received_value['value'] = value
        c = channels.Channel("bla",callback=cbk)
        cbk_event.wait(1.)
        self.assertTrue(received_value['value']=='hello')
        p.join()

    def testRaiseExceptionInCallback(self):
        c = channels.Channel("test_exception")
        exception_raised = {"exc":False}
        def cbk(value,exception_raised = exception_raised):
            try:
                c.value = "bla"
            except RuntimeError:
                exception_raised['exc'] = True
        c.register_callback(cbk)
        
        c.value = "tagada"
        self.assertTrue(exception_raised['exc'])

if __name__ == '__main__':
    unittest.main()
