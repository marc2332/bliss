# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import gevent

from bliss.controllers import keithley
from bliss.common import proxy
from bliss.comm import rpc
from bliss import global_map

from .counter import _LocalClientCounter

from . import (
    register_local_client_callback,
    register_local_server_callback,
    add_local_server_object,
)

# Base Sensor (SCPI)
# --- Client side ---
class _LocalSensor(_LocalClientCounter):
    def __init__(self, client, port, config):
        super().__init__(client, port, config)
        global_map.register(self, parents_list=["counters"])


add_local_server_object(_LocalSensor)

# --- Server side ---
def _server_keithley_sensor(obj, start_sub_server):
    comm = obj.comm
    comm_port = start_sub_server(comm)

    controller = obj.controller
    controller_port = start_sub_server(controller)

    cc_controller = obj._counter_controller
    cc_controller_port = start_sub_server(cc_controller)

    hostname = gevent.socket.gethostname()

    class Sensor(proxy.Proxy):
        __target__ = obj

        @property
        def comm(self):
            return rpc._SubServer(f"tcp://{hostname}:{comm_port}")

        @property
        def controller(self):
            return rpc._SubServer(f"tcp://{hostname}:{controller_port}")

        @property
        def _counter_controller(self):
            return rpc._SubServer(f"tcp://{hostname}:{cc_controller_port}")

    return Sensor(None)


# DDC
# --- Client side ---
class _LocalDDCSensor(proxy.Proxy):
    __slots__ = list(proxy.Proxy.__slots__) + ["_counters_controller"]

    def __init__(self, client, port, config):
        super().__init__(None)
        self.__target__ = client
        self._counters_controller = keithley.AmmeterDDCCounterController(
            "keithley", client.interface
        )
        global_map.register(self, parents_list=["counters"])


# --- Server side ---
def _server_keithley_ddc(obj, start_sub_server):
    interface = obj.interface
    port = start_sub_server(interface)
    hostname = gevent.socket.gethostname()

    class Cnt(proxy.Proxy):
        __target__ = obj

        @property
        def interface(self):
            return rpc._SubServer(f"tcp://{hostname}:{port}")

    return Cnt(None)


def init():
    # Sensor
    # --- SCPI ---
    register_local_client_callback(keithley.BaseSensor, _LocalSensor, priority=20)
    register_local_server_callback(
        keithley.BaseSensor, _server_keithley_sensor, priority=20
    )
    # --- DDC ---
    register_local_client_callback(
        keithley.AmmeterDDC.Sensor, _LocalDDCSensor, priority=20
    )
    register_local_server_callback(
        keithley.AmmeterDDC.Sensor, _server_keithley_ddc, priority=20
    )
