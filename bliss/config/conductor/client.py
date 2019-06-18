# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os, sys
import io
from . import connection
from .connection import StolenLockException
from functools import wraps

_default_connection = None


def get_default_connection():
    global _default_connection
    if _default_connection is None:
        _default_connection = connection.Connection()
    return _default_connection


class _StringIO(io.StringIO):
    def __enter__(self, *args, **kwags):
        return self

    def __exit__(self, *args, **kwags):
        pass


class _BytesIO(io.BytesIO):
    def __enter__(self, *args, **kwags):
        return self

    def __exit__(self, *args, **kwags):
        pass


def check_connection(func):
    @wraps(func)
    def f(*args, **keys):
        keys["connection"] = keys.get("connection") or get_default_connection()
        return func(*args, **keys)

    return f


class Lock(object):
    def __init__(self, *devices, **params):
        """
        This class is an helper to lock object using context manager
        :params timeout default 10s
        :params priority default 50
        """
        self._devices = devices
        self._params = params

    def __enter__(self):
        lock(*self._devices, **self._params)
        return self

    def __exit__(self, *args, **kwags):
        unlock(*self._devices, **self._params)


def synchronized(**params):
    """
    Synchronization decorator.

    This is an helper to lock during the method call.
    :params are the lock's parameters (see Lock helper)
    """

    def wrap(f):
        @wraps(f)
        def func(self, *args, **keys):
            with Lock(self, **params):
                return f(self, *args, **keys)

        return func

    return wrap


@check_connection
def lock(*devices, **params):
    devices_name = [d.name for d in devices]
    params["connection"].lock(devices_name, **params)


@check_connection
def unlock(*devices, **params):
    devices_name = [d.name for d in devices]
    params["connection"].unlock(devices_name, **params)


@check_connection
def get_cache_address(connection=None):
    return connection.get_redis_connection_address()


@check_connection
def get_redis_connection(db=0, connection=None):
    return connection.get_redis_connection(db=db)


@check_connection
def clean_all_redis_connection(connection=None):
    return connection.clean_all_redis_connection()


@check_connection
def get_config_file(file_path, connection=None):
    return connection.get_config_file(file_path)


def get_text_file(file_path, connection=None):
    return get_config_file(file_path).decode()


def get_file(
    config_node, key, local=False, base_path=None, raise_on_none_path=True, text=False
):
    """
    return an open file object in read only mode.

    This function first try to open a remote file store on the global configuration.
    If it failed it try to open it locally like python *open*.

    :params config_node basically the controller's configuration node.
    :params key the config_node[key] where the file path is stored.
    If config_node[key] start with './' => the path will be relative to the config_node file.
    :params local if set to True, just use python *open*
    :params base_path path prepended if not None to the path return by config_node[key]
    :params raise_on_none_path if False and config_node[key] == None, return empty file. Otherwise raise KeyError.
    this parameters may be useful if the key is optional.
    """
    path = config_node.get(key)
    if path is not None:
        if base_path is not None:
            path = os.path.join(base_path, path)
        elif path.startswith("."):  # relative from current config_node
            base_path = os.path.dirname(config_node.filename)
            path = os.path.join(base_path, path)
    elif raise_on_none_path:
        raise KeyError(key)
    return _open_file(path, local, text=text)


def remote_open(file_path, local=False, text=False):
    """
    return an open file object in read only mode

    :params file_path the full path to the file if None return an empty file
    :params local if set to True, just use python *open*
    """
    return _open_file(file_path, local, text=text)


def _open_file(file_path, local, text=False):
    if file_path is None:
        return _StringIO() if text else _BytesIO()

    if local:
        return open(file_path, "r" if text else "rb")

    if sys.platform in ["win32", "cygwin"]:
        file_path = file_path.replace("\\", "/")

    try:
        file_content = get_config_file(file_path.strip("/"))
    except RuntimeError:
        return open(file_path, "r" if text else "rb")
    else:
        return _StringIO(file_content.decode()) if text else _BytesIO(file_content)


@check_connection
def get_config_db_files(base_path="", timeout=3.0, connection=None):
    """
       Gives a sequence of pairs: (file name<str>, file content<str>)

       :param base_path:
           base path to start looking for db files [default '', meaning use

       :type base_path: str
       :param timeout: timeout (seconds)
       :type timeoout: float
       :param connection:
           connection object [default: None, meaning use default connection]
       :return:
           a sequence of pairs: (file name<str>, file content<str>)
    """
    path2files = connection.get_config_db(base_path=base_path, timeout=timeout)
    return path2files


@check_connection
def get_config_db_tree(base_path="", timeout=3.0, connection=None):
    """
    """
    return connection.get_config_db_tree(base_path, timeout=timeout)


@check_connection
def set_config_db_file(filepath, content, timeout=3.0, connection=None):
    connection.set_config_db_file(filepath, content, timeout=timeout)


@check_connection
def remove_config_file(file_path, connection=None):
    return connection.remove_config_file(file_path)


@check_connection
def move_config_path(src_path, dst_path, connection=None):
    return connection.move_config_path(src_path, dst_path)


@check_connection
def get_python_modules(base_path="", timeout=3.0, connection=None):
    return connection.get_python_modules(base_path, timeout)
