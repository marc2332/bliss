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
import gipc
import signal
import gc

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
    with pytest.raises(ValueError):
        c1.register_callback(None)

def test_channel_unref(beacon):
    c = channels.Channel("test_chan", "test")
    del c
    c = channels.Channel("test_chan", "test")
    assert c.value == 'test'

def test_channel_unref2(beacon):
    c = channels.Channel("test_chan2")
    channels.Channel("test_chan2", "test")
    assert c.value == 'test'

def test_with_another_process(beacon, beacon_host_port):
    def child_process(child_end, beacon_host_port):
        from bliss.config.conductor import client
        from bliss.config.conductor import connection
        from bliss.config import channels
        import sys
        beacon_connection = connection.Connection(*beacon_host_port)
        client._default_connection = beacon_connection
        channels.Bus._CACHE = dict()

        assert child_end.get() == '!'
        child_end.put('$')

        chan = channels.Channel("test_chan")
        if chan.value == 'helloworld':
            chan.value = 'bla'
            child_end.put('#')
            if child_end.get() == '.':
                sys.exit(2)

    c = channels.Channel("test_chan", "helloworld")

    with gipc.pipe(duplex=True) as (child_end, parent_end):
        p = gipc.start_process(target=child_process, args=(child_end,
                                                           beacon_host_port))
        parent_end.put('!')
        assert parent_end.get() == '$'
        assert parent_end.get() == '#'
        gevent.sleep(0.1) #time for value to be received
        assert c.value == 'bla'
        assert len(gc.get_referrers(c)) == 1
        del c
        # check channel is really not there anymore
        redis = channels.client.get_cache()
        bus = channels.Bus._CACHE[redis]
        assert 'test_chan' not in bus._channels
        #
        os.kill(p.pid, signal.SIGSTOP)
        cc = channels.Channel("test_chan")
        cc.timeout = 0.1
        with pytest.raises(RuntimeError):
            assert cc.value == 'bla'
        os.kill(p.pid, signal.SIGCONT)
        assert cc.value == 'bla'
        parent_end.put('.')
        p.join()
        assert p.exitcode == 2
