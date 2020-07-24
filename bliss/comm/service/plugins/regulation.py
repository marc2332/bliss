# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import copyreg
import gevent

from bliss.common import protocols
from bliss.common import regulation, proxy
from bliss.common import counter
from bliss.comm import rpc
from bliss import global_map

from . import (
    register_local_client_callback,
    register_local_server_callback,
    add_local_server_object,
)
from .counter import _LocalCounterController

# Input and Output temperature object

# --- Client Side ---
class _LocalSamplingCounter(counter.SamplingCounter):
    pass


# Don't need any information in **read** so counter can be None
def _None(*args):
    return None


def _pickle_None(*args):
    return _None, ()


copyreg.pickle(_LocalSamplingCounter, _pickle_None)


class _LocalRegulationObject(_LocalCounterController):
    __slots__ = list(_LocalCounterController.__slots__) + ["_port"]

    def __init__(self, client, port, config):
        super().__init__(None)
        self._port = port
        self.__target__ = client
        global_map.register(self, parents_list=["counters"])

    @property
    def counters(self):
        return protocols.counter_namespace(
            [
                _LocalSamplingCounter(
                    self.name + "_counter",
                    self,
                    unit=self.config.get("unit", "N/A"),
                    mode=self.config.get("sampling-counter-mode", "SINGLE"),
                )
            ]
        )


add_local_server_object(_LocalRegulationObject)

# --- Server side ---
def _server_regulation_controller(obj, start_sub_server):
    ctrl = obj.controller
    port = start_sub_server(ctrl)
    hostname = gevent.socket.gethostname()

    class Cnt(proxy.Proxy):
        __target__ = obj

        @property
        def controller(self):
            return rpc._SubServer(f"tcp://{hostname}:{port}")

    return Cnt(None)


# Loop object
# --- Client side ---
class _LocalLoopObject(_LocalCounterController):
    __slots__ = list(proxy.Proxy.__slots__) + ["_port"]

    def __init__(self, client, port, config):
        super().__init__(None)
        self._port = port
        self.__target__ = client
        global_map.register(self, parents_list=["counters"])

    @property
    def input(self):
        remote_input = self.__target__.input
        connection_address = self.__target__.connection_address
        port = int(connection_address.split(":")[-1])
        return _LocalRegulationObject(remote_input, port, remote_input.config)

    @property
    def output(self):
        remote_output = self.__target__.output
        connection_address = self.__target__.connection_address
        port = int(connection_address.split(":")[-1])
        return _LocalRegulationObject(remote_output, port, remote_output.config)

    @property
    def counters(self):
        input_obj = self.input
        output_obj = self.output
        input_cnt = next(iter(input_obj.counters))
        setpoint_cnt = _LocalSamplingCounter(
            self.name + "_setpoint", self, unit=input_cnt.unit, mode="SINGLE"
        )
        return protocols.counter_namespace(
            [input_cnt, setpoint_cnt] + list(output_obj.counters)
        )


add_local_server_object(_LocalLoopObject)

# --- Server side ---
def _server_loop_regulation_controller(obj, start_sub_server):
    ctrl = obj.controller
    controller_port = start_sub_server(ctrl)
    hostname = gevent.socket.gethostname()

    input_object = obj.input
    input_port = start_sub_server(input_object)

    output_object = obj.output
    output_port = start_sub_server(output_object)

    class Cnt(proxy.Proxy):
        __target__ = obj

        @property
        def controller(self):
            return rpc._SubServer(f"tcp://{hostname}:{controller_port}")

        @property
        def input(self):
            return rpc._SubServer(f"tcp://{hostname}:{input_port}")

        @property
        def output(self):
            return rpc._SubServer(f"tcp://{hostname}:{output_port}")

    return Cnt(None)


def init():
    # Input
    register_local_client_callback(
        regulation.Input, _LocalRegulationObject, priority=20
    )
    register_local_server_callback(
        regulation.Input, _server_regulation_controller, priority=20
    )
    # Output
    register_local_client_callback(
        regulation.Output, _LocalRegulationObject, priority=20
    )
    register_local_server_callback(
        regulation.Output, _server_regulation_controller, priority=20
    )
    # Loop
    register_local_client_callback(regulation.Loop, _LocalLoopObject, priority=20)
    register_local_server_callback(
        regulation.Loop, _server_loop_regulation_controller, priority=20
    )
