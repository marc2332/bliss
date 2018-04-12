# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import gc
import signal

import gipc
import gevent
import pytest

from bliss.config import channels


def test_channel_not_initialized(beacon):
    c = channels.Channel("tagada")
    assert c.value is None


def test_channel_set(beacon):
    c = channels.Channel("super mario", "test")
    assert c.value == 'test'


def test_channel_cb(beacon):
    cb_dict = dict({"value": None, "exception": None})

    def cb(value):
        cb_dict['value'] = value
        if value == 'exception':
            try:
                c1.value = 'test'
            except RuntimeError:
                cb_dict['exception'] = True
                raise

    c1 = channels.Channel("super_mario", callback=cb)
    c2 = channels.Channel("super_mario")

    c2.value = 'toto'
    assert cb_dict['value'] == 'toto'

    c2.value = 'exception'
    assert cb_dict['exception']
    assert c1.value == 'exception'
    assert c2.value == 'exception'

    c2.unregister_callback(cb)
    c1.value = 1
    c2.value = 2
    assert cb_dict['value'] == 'exception'

    c2.unregister_callback(int)

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


def test_channel_default_value(beacon):
    c = channels.Channel('test_chan3', default_value=3)
    assert c.default_value == 3
    assert c.value == 3


def test_channel_repr(beacon):
    c = channels.Channel('test_chan4')
    assert 'test_chan4' in repr(c)
    assert 'initializing' in repr(c)
    value = c.value
    assert 'test_chan4' in repr(c)
    assert repr(value) in repr(c)


def test_channel_prevent_concurrent_queries(beacon):
    c = channels.Channel('test_chan5')
    with pytest.raises(RuntimeError) as info:
        c._start_query()
    assert 'already running' in str(info)


def test_channel_garbage_collection(beacon):
    # Subscribe
    c = channels.Channel('test_chan6')
    c.value = 3
    gevent.sleep(0.1)
    assert len(gc.get_referrers(c)) == 1
    del c

    # Still subscribed
    c = channels.Channel('test_chan6')
    assert c.value is None


def test_with_another_process(beacon, beacon_host_port):
    def child_process(child_end, beacon_host_port):

        import sys
        from bliss.config.conductor import client
        from bliss.config.conductor import connection
        from bliss.config import channels

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
        p = gipc.start_process(
            target=child_process, args=(child_end, beacon_host_port))

        # Synchronize
        parent_end.put('!')
        assert parent_end.get() == '$'
        assert parent_end.get() == '#'

        # Wait for new value
        gevent.sleep(0.1)
        assert c.value == 'bla'
        assert len(gc.get_referrers(c)) == 1
        del c

        # Check channel is really not there anymore
        redis = channels.client.get_cache()
        bus = channels.Bus._CACHE[redis]
        assert 'test_chan' not in bus._channels

        # Pause subprocess
        os.kill(p.pid, signal.SIGSTOP)

        # New channel
        cc = channels.Channel("test_chan")
        cc.timeout = 0.1
        assert cc.timeout == 0.1

        # Make sure it times out
        with pytest.raises(RuntimeError):
            assert cc.value == 'bla'

        # Restore subprocess
        os.kill(p.pid, signal.SIGCONT)

        # Make sure the value is now received
        assert cc.value == 'bla'

        # Synchronize with subprocess
        parent_end.put('.')
        p.join()
        assert p.exitcode == 2
