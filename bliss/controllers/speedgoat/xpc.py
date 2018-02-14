# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

import os
import operator
import functools

import numpy
from ._cffi import xpc, ffi

DEFAULT_SPEEDGOAT_PORT = 22222


class SimulinkError(Exception):
    pass


def _discover():
    """
    In case most of the functions don't need translation we can apply this to
    auto populate the module with xpc methods
    """
    import re

    first_cap_re = re.compile("(.)([A-Z][a-z]+)")
    all_cap_re = re.compile("([a-z0-9])([A-Z])")

    def camelCase_to_snake(name):
        s1 = first_cap_re.sub(r"\1_\2", name)
        return all_cap_re.sub(r"\1_\2", s1).lower()

    items = {}
    for name in dir(xpc):
        item = getattr(xpc, name)
        if name.startswith("xPC") and callable(item):
            name = camelCase_to_snake(name[3:])
            items[name] = item
    globals().update(items)


_discover()

# Connection


def tcp_connect(host, port):
    host = host.encode("ascii")
    port = str(port).encode("ascii")
    handle = xpc.xPCOpenTcpIpPort(host, port)
    if handle == -1:
        raise SimulinkError("Unable to connect to {}:{}".format(host, port))
    return handle


def close_port(handle):
    if handle is None:
        return
    xpc.xPCClosePort(handle)


# Miscellaneous


def get_api_version(handle=None):
    buff = xpc.xPCGetAPIVersion()
    return ffi.string(buff).decode()


def get_target_version(handle):
    buff = ffi.new("char[64]")
    xpc.xPCGetTargetVersion(handle, buff)
    return ffi.string(buff).decode()


def ping(handle):
    return xpc.xPCTargetPing(handle)


def get_last_error_message(handle):
    errno = xpc.xPCGetLastError()
    if errno == xpc.ENOERR:
        return
    buff = ffi.new("char[256]")
    xpc.xPCErrorMsg(handle, errno, buff)
    return ffi.string(buff).decode()


# Application


def get_app_name(handle):
    buff = ffi.new("char[256]")
    xpc.xPCGetAppName(handle, buff)
    return ffi.string(buff).decode()


# discovered:
# start_app
# stop_app
# unload_app


def load_app(handle, path, fname):
    xpc.xPCLoadApp(handle, path.encode("ascii"), fname.encode("ascii"))


# Parameters

"""
def get_num_params(handle):
    return xpc.xPCGetNumParams(handle)
"""


def get_param_idx(handle, block, name):
    return xpc.xPCGetParamIdx(handle, block.encode("ascii"), name.encode("ascii"))


def get_param(handle, idx):
    block = ffi.new("char[2048]")
    param = ffi.new("char[256]")
    ptype = ffi.new("char[64]")
    dims = ffi.new("int[8]")
    xpc.xPCGetParamName(handle, idx, block, param)
    xpc.xPCGetParamType(handle, idx, ptype)
    num_dims = xpc.xPCGetParamDimsSize(handle, idx)
    xpc.xPCGetParamDims(handle, idx, dims)
    shape, size = [], 1
    for dim in dims[0:num_dims]:
        if size == 1 and dim == 1:
            continue
        empty = False
        shape.append(dim)
        size *= dim
    path = ffi.string(block).decode()
    name = ffi.string(param).decode()
    dtype = ffi.string(ptype).decode().lower()
    if dtype == "boolean":
        dtype = "bool"
    full_name = "{}@{}".format(name, path)
    return dict(
        name=name,
        path=path,
        full_name=full_name,
        dtype=dtype,
        idx=idx,
        shape=shape,
        size=size,
    )


def get_params(handle):
    return [get_param(handle, i) for i in range(get_num_params(handle))]


def get_param_value_from_name(handle, block, name):
    idx = get_param_idx(handle, block, name)
    return get_param_value_from_idx(handle, idx)


def get_param_value_from_idx(handle, idx):
    param = get_param(handle, idx)
    return get_param_value(handle, param)


def get_param_value(handle, param):
    shape, size, dtype = param["shape"], param["size"], param["dtype"]
    # if dtype != 'double':
    #    raise NotImplementedError('Cannot handle {!r} type yet!'.format(dtype))
    values = numpy.empty(shape, dtype="double", order="F")
    buff = ffi.cast("double *", values.ctypes.data)
    xpc.xPCGetParam(handle, param["idx"], buff)
    values = values.astype(dtype)
    if size == 1:
        return numpy.asscalar(values)
    # values.shape = param['shape']
    return values


def set_param_value_from_name(handle, block, name, value):
    idx = get_param_idx(handle, block, name)
    return set_param_value_from_idx(handle, idx, value)


def set_param_value_from_idx(handle, idx, value):
    param = get_param(handle, idx)
    return set_param_value(handle, param, value)


def set_param_value(handle, param, value):
    shape, size, dtype = param["shape"], param["size"], param["dtype"]
    value = numpy.array(value, dtype="double", copy=False, order="F")
    value.shape = shape
    assert value.size == size, "size mismatch"
    buff = ffi.cast("double *", value.ctypes.data)
    xpc.xPCSetParam(handle, param["idx"], buff)


# Signals

"""
def get_num_signals(handle):
    return xpc.xPCGetNumSignals(handle)
"""


def get_signal(handle, idx):
    width = xpc.xPCGetSignalWidth(handle, idx)
    name = ffi.new("char[256]")
    xpc.xPCGetSignalName(handle, idx, name)
    name = ffi.string(name)
    result = dict(name=name, width=width, idx=idx)
    label_size = xpc.xPCGetSigLabelWidth(handle, name)
    if label_size > 0:
        label = ffi.new("char[{}]".format(label_size))
        xpc.xPCGetSignalLabel(handle, idx, label)
        result["label"] = ffi.string(label)
    return result


def get_signals(handle):
    return [get_signal(handle, i) for i in range(get_num_signals(handle))]


def get_signal_value(handle, idx):
    return xpc.xPCGetSignal(handle, idx)


def get_signal_values(handle, signals=None):
    if signals is None:
        signals = tuple(range(get_num_signals(handle)))
    n = len(signals)
    values = numpy.empty(n)
    buff = ffi.cast("double *", values.ctypes.data)
    xpc.xPCGetSignals(handle, n, signals, buff)
    return values


# Main


def main(argv=None):
    if argv is None:
        from sys import argv
    url = argv[1]
    host, port = url.rsplit(":", 1) if ":" in url else (url, "22222")
    return tcp_connect(host, port)


if __name__ == "__main__":
    simulink = main()
