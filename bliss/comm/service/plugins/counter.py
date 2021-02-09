# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import copyreg
import gevent
import weakref

from bliss.common import counter, proxy
from bliss.comm import rpc
from . import (
    register_local_client_callback,
    register_local_server_callback,
    add_local_server_object,
)


class _LocalCounterController(proxy.Proxy):
    __slots__ = list(proxy.Proxy.__slots__) + ["_counters"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._counters = weakref.WeakValueDictionary()

    def create_chain_node(self):
        # This has to be Local not remote
        klass = getattr(self.__target__, "__class__")
        return klass.create_chain_node(self)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        # This has to be Local not remote
        klass = getattr(self.__target__, "__class__")
        return klass.get_acquisition_object(
            self, acq_params, ctrl_params, parent_acq_params
        )

    def __eq__(self, other):
        try:
            obj = other.__wrapped__
        except AttributeError:
            return False
        else:
            return (
                obj._rpc_connection.address == self.__target__._rpc_connection.address
            )

    def __hash__(self):
        return id(self.__target__)


class _LocalClientCounter(proxy.Proxy):
    __slots__ = list(proxy.Proxy.__slots__) + ["_port"]

    def __init__(self, client, port, config):
        super().__init__(None)
        self._port = port
        self.__target__ = client

    @property
    def _counter_controller(self):
        cc_client = self.__target__._counter_controller
        controller = _LocalCounterController(None)
        controller.__target__ = cc_client
        return controller

    @property
    def shape(self):
        return tuple(self.__target__.shape)


add_local_server_object(_LocalClientCounter)


def _server_counter_controller(obj, start_sub_server):
    cc = obj._counter_controller
    port = start_sub_server(cc)
    hostname = gevent.socket.gethostname()

    class Cnt(proxy.Proxy):
        __target__ = obj

        @property
        def _counter_controller(self):
            return rpc._SubServer(f"tcp://{hostname}:{port}")

    return Cnt(None)


def init():
    register_local_client_callback(counter.Counter, _LocalClientCounter)
    register_local_server_callback(counter.Counter, _server_counter_controller)
