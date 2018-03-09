# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools

from . import xpc


def _to_host_port(url, default_port=None):
    pars = url.rsplit(":", 1) if isinstance(url, str) else url
    port = int(pars[1]) if len(pars) > 1 else default_port
    return pars[0], port


def _auto_connect(func):
    @functools.wraps(func)
    def wrapper(self, *args):
        if self._handle is None:
            self._handle = xpc.tcp_connect(self._host, self._port)
        xpc.open_connection(self._handle)
        return func(self._handle, *args)

    return wrapper


def _fill_methods(cls):
    filt = "tcp_connect", "close_port", "open_connection", "close_connection"
    for name in dir(xpc):
        if name.startswith("_") or name in filt or hasattr(cls, name):
            continue
        item = getattr(xpc, name)
        if not callable(item):
            continue
        setattr(cls, name, _auto_connect(item))
    return cls


@_fill_methods
class Speedgoat(object):
    def __init__(self, host, port=22222):
        self._host, self._port = _to_host_port(host, port)
        self._handle = None

    def close_connection(self):
        if self._handle is None:
            return
        xpc.close_connection(self._handle)

    def get_api_version(self):
        return xpc.get_api_version()


def main(argv=None):
    if argv is None:
        from sys import argv
    return Speedgoat(str(argv[1]))


if __name__ == "__main__":
    speedgoat = main()
