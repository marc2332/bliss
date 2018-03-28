# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
import gevent
import time
from bliss.config import channels

def test_channel_not_initialized(beacon):
    c = channels.Channel("tagada")
    assert c.value is None

def test_channel_set(beacon):
    c = channels.Channel("super mario", "test")
    assert c.value == 'test'

def test_channel_cb(beacon):
    cb_dict = dict({"value":None, "exception":None})
    c1 = channels.Channel("super_mario")
    
    def cb(value, saved_value=cb_dict, chan=c1):
        saved_value['value'] = value
        if value == 'exception':
            try:
                chan.value = 'test'
            except RuntimeError:
                saved_value['exception']=True

    c1.register_callback(cb)
    c2 = channels.Channel("super_mario")
    c2.value = 'toto'
    assert cb_dict['value'] == 'toto'
    c2.value = 'exception'
    assert cb_dict['exception']

def test_channel_unref(beacon):
    c = channels.Channel("test_chan", "test")
    del c
    c = channels.Channel("test_chan", "test")
    assert c.value == 'test'

def test_channel_unref2(beacon):
    c = channels.Channel("test_chan2")
    channels.Channel("test_chan2", "test")
    assert c.value == 'test'

"""
    def testTimeout(self):
        p, pipe, queue = test_ext_channel(3, "test2", "hello")
        pipe.recv()
        os.kill(p.pid, signal.SIGSTOP)
        c = channels.Channel("test2")
        self.assertEquals(c.timeout, 3)
        c.timeout = .5

        def get_value(c):
            return c.value

        t0 = time.time()
        self.assertRaises(RuntimeError, get_value, c)
        self.assertTrue(time.time()-t0 >= .5)
        os.kill(p.pid, signal.SIGCONT)
        self.assertEquals(c.value, "hello")
        p.join()
"""
