# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import os
import functools
import traceback
import pkgutil
import copyreg

_CLIENT_LOCAL_CALLBACK = dict()
_SERVER_LOCAL_CALLBACK = dict()
_INIT_FLAG = False


def _init_plugins():
    for importer, module_name, _ in pkgutil.iter_modules(
        [os.path.dirname(__file__)], prefix="bliss.comm.service.plugins."
    ):
        m = __import__(module_name, globals(), locals(), [""], 0)
        if not hasattr(m, "init"):
            continue
        try:
            m.init()
        except:
            traceback.print_exc()


def _check_init(func):
    @functools.wraps(func)
    def f(*args, **keys):
        global _INIT_FLAG
        if not _INIT_FLAG:
            _init_plugins()
            _INIT_FLAG = True
        return func(*args, **keys)

    return f


def _prio_sort(item):
    return item[1][0]


def register_local_client_callback(object_type, cbk, priority=0):
    _CLIENT_LOCAL_CALLBACK[object_type] = priority, cbk


def register_local_server_callback(object_type, cbk, priority=0):
    _SERVER_LOCAL_CALLBACK[object_type] = priority, cbk


@_check_init
def get_local_client(client, port, config):
    for object_type, (priority, cbk) in sorted(
        _CLIENT_LOCAL_CALLBACK.items(), key=_prio_sort, reverse=True
    ):
        if isinstance(client, object_type):
            return cbk(client, port, config)
    return client


@_check_init
def get_local_server(obj, start_sub_server):
    for object_type, (priority, cbk) in sorted(
        _SERVER_LOCAL_CALLBACK.items(), key=_prio_sort, reverse=True
    ):
        if isinstance(obj, object_type):
            return cbk(obj, start_sub_server)
    return obj


# Local server object
def _LocalServerObject(port):
    from .. import get_object_from_port

    return get_object_from_port(port)


def _pickle_LocalServerObject(local_object):
    return _LocalServerObject, (local_object._port,)


def add_local_server_object(klass):
    """
    If some objects need to be pickle from the client to
    the server.
    The matching is done by the port number locally.
    So on the client side the object need to store the
    distant server port for this object as **_port**
    """
    copyreg.pickle(klass, _pickle_LocalServerObject)
