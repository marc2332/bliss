# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import socket
import gevent
import pytest

from bliss.config.conductor import client
from bliss.config import channels


def test_address_queries(new_beacon_connection):
    assert new_beacon_connection.get_redis_connection_address()
    assert new_beacon_connection.get_redis_data_server_connection_address()
    assert new_beacon_connection.get_log_server_address()


def test_client_name(beacon):
    conductor_conn = client.get_default_connection()
    conductor_conn.set_client_name("test")
    assert conductor_conn.get_client_name() == "test"


def test_lock(beacon):
    roby = beacon.get("roby")
    conductor_conn = client.get_default_connection()

    try:
        client.lock(roby)
        lock_owner = conductor_conn.who_locked(
            roby.name
        )  # why not client.who_locked(roby) ?
        assert lock_owner == {roby.name: f"{socket.gethostname()}:{os.getpid()}"}
    finally:
        client.unlock(roby)
    assert not conductor_conn.who_locked(roby.name)


def test_who_locked_client_name(beacon):
    roby = beacon.get("roby")
    conductor_conn = client.get_default_connection()
    conductor_conn.set_client_name("test")

    try:
        client.lock(roby)
        lock_owner = conductor_conn.who_locked(roby.name)
        assert lock_owner == {roby.name: "test"}
    finally:
        client.unlock(roby)
    assert not conductor_conn.who_locked(roby.name)


def test_2_clients_lock(beacon, two_clients):
    conductor_conn, conductor_proxy2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)  # could return True if successful ?
    # assert conductor_conn.lock(roby.name)
    with pytest.raises(RuntimeError):
        conductor_proxy2.lock(roby.name, timeout=0.1)
    conductor_conn.unlock(roby.name)
    conductor_proxy2.lock(roby.name)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test2"}


def test_lock_priority(beacon, two_clients):
    conductor_conn, conductor_proxy2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)  # normal priority is 50
    conductor_proxy2.lock(roby.name, priority=100)  # famous 'lock stealing'
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test2"}
    conductor_conn.lock(roby.name, priority=200)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test1"}


def test_2_clients_1_dead(beacon, two_clients):
    conductor_conn, conductor_proxy2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test1"}
    conductor_conn.close()
    with gevent.Timeout(3):
        while conductor_proxy2.who_locked(roby.name):
            gevent.sleep(0.1)
    conductor_proxy2.lock(roby.name)
    assert conductor_proxy2.who_locked(roby.name) == {roby.name: "test2"}


def test_single_bus_for_channels(beacon):
    key = "multi_green"
    value = "hello"

    def get_channel_on_different_greenlet():
        c = channels.Channel(key, default_value=value)
        gevent.sleep(0)  # give hand to other greenlet
        return c, c.value

    chan = channels.Channel(key, default_value=value)
    chan_task = [gevent.spawn(get_channel_on_different_greenlet) for i in range(3)]

    gevent.joinall(chan_task, timeout=10, raise_error=True)
    assert value == chan.value
    assert all([value == t.get()[1] for t in chan_task])
    buses = set([chan._bus] + [t.get()[0]._bus for t in chan_task])
    assert len(buses) == 1
    chan._bus.close()
