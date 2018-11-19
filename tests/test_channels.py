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
    assert c.timeout == 3.
    assert c.value is None


def test_channel_set(beacon):
    c = channels.Channel("super mario", "test")
    assert c.value == "test"


def test_channel_cb(beacon):
    cb_dict = dict({"value": None, "exception": None})

    def cb(value):
        cb_dict["value"] = value
        if value == "exception":
            try:
                c1.value = "test"
            except RuntimeError:
                cb_dict["exception"] = True
                raise

    c1 = channels.Channel("super_mario", callback=cb)
    c2 = channels.Channel("super_mario")

    c2.value = "toto"
    assert cb_dict["value"] == "toto"

    c2.value = "exception"
    assert cb_dict["exception"]
    assert c1.value == "exception"
    assert c2.value == "exception"

    c2.unregister_callback(cb)
    c1.value = 1
    c2.value = 2
    assert cb_dict["value"] == "exception"

    c2.unregister_callback(int)

    with pytest.raises(ValueError):
        c1.register_callback(None)


def test_channel_unref(beacon):
    c = channels.Channel("test_chan", "test")
    del c
    c = channels.Channel("test_chan", "test")
    assert c.value == "test"


def test_channel_unref2(beacon):
    c = channels.Channel("test_chan2")
    channels.Channel("test_chan2", "test")
    assert c.value == "test"


def test_channel_default_value(beacon):
    c = channels.Channel("test_chan3", default_value=3)
    assert c.default_value == 3
    assert c.value == 3


def test_channel_repr(beacon):
    c = channels.Channel("test_chan4")
    assert "test_chan4" in repr(c)
    assert "initializing" in repr(c)
    value = c.value
    assert "test_chan4" in repr(c)
    assert repr(value) in repr(c)


def test_channel_prevent_concurrent_queries(beacon):
    c1 = channels.Channel("test_chan5")
    query_task = c1._query_task
    c2 = channels.Channel("test_chan5")
    assert query_task == c2._query_task


def test_channel_garbage_collection(beacon):
    # Subscribe
    c = channels.Channel("test_chan6")
    c.value = 3
    gevent.sleep(0.1)
    assert len(gc.get_referrers(c)) <= 1
    del c

    # Still subscribed
    c = channels.Channel("test_chan6")
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

        assert child_end.get() == "!"
        child_end.put("$")

        chan = channels.Channel("test_chan")
        if chan.value == "helloworld":
            chan.value = "bla"
            child_end.put("#")
            if child_end.get() == ".":
                sys.exit(2)

    c = channels.Channel("test_chan", "helloworld")

    with gipc.pipe(duplex=True) as (child_end, parent_end):
        p = gipc.start_process(target=child_process, args=(child_end, beacon_host_port))

        # Synchronize
        parent_end.put("!")
        assert parent_end.get() == "$"
        assert parent_end.get() == "#"

        # Wait for new value
        gevent.sleep(0.1)
        assert c.value == "bla"
        assert len(gc.get_referrers(c)) <= 1
        del c

        # Check channel is really not there anymore
        redis = channels.client.get_cache()
        bus = channels.Bus._CACHE[redis]
        assert "test_chan" not in bus._channels

        # Pause subprocess
        os.kill(p.pid, signal.SIGSTOP)

        # New channel
        cc = channels.Channel("test_chan", timeout=0.5)
        assert cc.timeout == 0.5
        cc.timeout = 0.1
        assert cc.timeout == 0.1

        # Make sure it times out
        with pytest.raises(RuntimeError):
            assert cc.value == "bla"

        # Restore subprocess
        os.kill(p.pid, signal.SIGCONT)

        # Make sure the value is now received
        assert cc.value == "bla"

        # Synchronize with subprocess
        parent_end.put(".")
        p.join()
        assert p.exitcode == 2


def test_channels_advanced(beacon):
    bus1 = channels.Bus()
    bus2 = channels.Bus.instanciate(bus1._redis)

    # Create channel 1
    c1 = channels.Channel("test_chan7", bus=bus1)
    assert c1.value is None

    # Channel 1 is unreferenced but not unsubscribed
    del c1
    assert bus1.get_channel("test_chan7") is None
    assert "test_chan7" in bus1._current_subs

    # Create channel 2 and makes sure it works correctly
    c2 = channels.Channel("test_chan7", bus=bus2)
    assert c2.value is None
    c2.value = 2
    assert c2.value == 2

    # Wait and perform another update
    gevent.sleep(0.1)
    c2.value = 3
    assert c2.value == 3

    # Re-instanciate channel 1
    c1 = channels.Channel("test_chan7", bus=bus1)
    assert c1.value == 3

    # Close bus 2
    bus2.close()


def test_channels_cache(beacon):
    # Make sure the cache is clear
    channels.DEVICE_CACHE.clear()

    # Create a device
    dev = lambda: None
    dev.name = "device"

    # Create a cached channel
    dev.attr = channels.Cache(dev, "attr")
    assert dev.attr.name == "device:attr"
    dev.attr.value = 1
    assert dev.attr.value == 1

    # Clear the cache for all devices
    assert len(channels.DEVICE_CACHE) == 1
    channels.clear_cache()
    assert dev.attr.value is None

    # Cached channels are weakly referenced
    del dev
    assert len(channels.DEVICE_CACHE) == 0

    # A device needs a name
    with pytest.raises(TypeError) as info:
        channels.Cache(1, "attr")
    assert "the device 1 has no name" in str(info)


def test_2processes_set_channel_value_constructor(beacon, beacon_host_port):
    def child_process(child_end, beacon_host_port):
        import sys
        from bliss.config.conductor import client
        from bliss.config.conductor import connection
        from bliss.config import channels

        beacon_connection = connection.Connection(*beacon_host_port)
        client._default_connection = beacon_connection
        channels.Bus._CACHE = dict()

        assert child_end.get() == "!"

        chan = channels.Channel("test_chan", value="test")
        child_end.put("$")
        if child_end.get() == ".":
            sys.exit(0)

    c = channels.Channel("test_chan")

    with gipc.pipe(duplex=True) as (child_end, parent_end):
        p = gipc.start_process(target=child_process, args=(child_end, beacon_host_port))

        # Synchronize
        parent_end.put("!")
        assert parent_end.get() == "$"
        gevent.sleep(0.1)
        try:
            assert c.value == "test"
        finally:
            parent_end.put(".")
            p.join()
