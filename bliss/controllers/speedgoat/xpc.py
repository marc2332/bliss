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


def _to_bytes(arg):
    if isinstance(arg, bytes):
        return arg
    return arg.encode()


def _error(result):
    err = get_last_error_msg()
    if err is None:
        return result
    raise SimulinkError(err)


def _error_handle(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return _error(func(*args, **kwargs))

    return wrapper


def struct_to_dict(data):
    return {k: getattr(data, k) for k in dir(data) if not k.startswith("_")}


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
            items[name] = _error_handle(item)
    globals().update(items)


_discover()

# Connection


def tcp_connect(host, port):
    bhost = _to_bytes(host)
    bport = _to_bytes(str(port))
    handle = xpc.xPCOpenTcpIpPort(bhost, bport)
    if handle == -1:
        raise SimulinkError("Unable to connect to {}:{}".format(host, port))
    return handle


def close_port(handle):
    if handle is None:
        return
    xpc.xPCClosePort(handle)


# Miscellaneous


def get_api_version():
    buff = xpc.xPCGetAPIVersion()
    return ffi.string(buff).decode()


def get_target_version(handle):
    buff = ffi.new("char[64]")
    xpc.xPCGetTargetVersion(handle, buff)
    return ffi.string(buff).decode()


def get_pci_info(handle):
    buff = ffi.new("char[8192]")
    _error(xpc.xPCGetPCIInfo(handle, buff))
    return ffi.string(buff).decode()


def ping(handle):
    return _error(xpc.xPCTargetPing(handle))


def get_last_error():
    return xpc.xPCGetLastError()


def error_msg(errno):
    buff = ffi.new("char[256]")
    xpc.xPCErrorMsg(errno, buff)
    return ffi.string(buff).decode()


def get_last_error_msg():
    errno = get_last_error()
    if errno == xpc.ENOERR:
        return
    return error_msg(errno)


def get_system_state(handle):
    """Helper to get all system information"""
    attrs = (
        "target_version",
        "exec_time",
        "sim_mode",
        "session_time",
        "stop_time",
        "load_time_out",
        "sample_time",
        "echo",
        "hidden_scope_echo",
        "app_name",
        "num_params",
        "num_signals",
        "num_scopes",
    )
    space = globals()
    result = {name: space["get_" + name](handle) for name in attrs}
    result["api_version"] = get_api_version()
    result["is_app_running"] = is_app_running(handle)
    result["is_overloaded"] = is_overloaded(handle)
    return result


# Application


def get_app_name(handle):
    buff = ffi.new("char[256]")
    _error(xpc.xPCGetAppName(handle, buff))
    return ffi.string(buff).decode()


def is_app_running(handle):
    return bool(_error(xpc.xPCIsAppRunning(handle)))


def is_overloaded(handle):
    return bool(_error(xpc.xPCIsOverloaded(handle)))


# discovered:
# start_app
# stop_app
# unload_app


def load_app(handle, path, fname):
    _error(xpc.xPCLoadApp(handle, _to_bytes(path), _to_bytes(fname)))


# Parameters

"""
def get_num_params(handle):
    return xpc.xPCGetNumParams(handle)
"""


def get_param_idx(handle, block, name):
    return _error(xpc.xPCGetParamIdx(handle, _to_bytes(block), _to_bytes(name)))


def get_param_idxs(handle, *block_names):
    if not block_names:
        return range(get_num_params(handle))
    return [get_param_idx(handle, *block_name) for block_name in block_names]


def get_param_name(handle, idx):
    block = ffi.new("char[2048]")
    name = ffi.new("char[256]")
    _error(xpc.xPCGetParamName(handle, idx, block, name))
    return ffi.string(block).decode(), ffi.string(name).decode()


def get_param_type(handle, idx):
    ptype = ffi.new("char[32]")
    _error(xpc.xPCGetParamType(handle, idx, ptype))
    dtype = ffi.string(ptype).decode().lower()
    if dtype == "boolean":
        dtype = "bool"
    return dtype


def get_param_shape(handle, idx):
    dims = ffi.new("int[8]")
    num_dims = _error(xpc.xPCGetParamDimsSize(handle, idx))
    _error(xpc.xPCGetParamDims(handle, idx, dims))
    shape, size = [], 1
    for dim in dims[0:num_dims]:
        if size == 1 and dim == 1:
            continue
        shape.append(dim)
        size *= dim
    return shape, size


def get_param_info(handle, idx):
    block, name = get_param_name(handle, idx)
    dtype = get_param_type(handle, idx)
    shape, size = get_param_shape(handle, idx)
    return dict(name=name, block=block, dtype=dtype, idx=idx, shape=shape, size=size)


def get_param_infos(handle, *idxs):
    if not idxs:
        idxs = range(get_num_params(handle))
    return [get_param_info(handle, idx) for idx in idxs]


def get_param_from_name(handle, block, name):
    idx = get_param_idx(handle, block, name)
    return get_param_from_idx(handle, idx)


def get_param_from_names(handle, *block_names):
    idxs = get_param_idxs(handle, *block_names)
    return get_param_from_idxs(handle, *idxs)


def get_param_value_from_name(handle, block, name):
    return get_param_from_name(handle, block, name)["value"]


def get_param_value_from_names(handle, *block_names):
    return [p["value"] for p in get_param_from_names(handle, *block_names)]


def get_param_from_idx(handle, idx):
    param_info = get_param_info(handle, idx)
    return get_param(handle, param_info)


def get_param_from_idxs(handle, *idxs):
    if not idxs:
        idxs = range(get_num_params(handle))
    return [get_param_from_idx(handle, idx) for idx in idxs]


def get_param_value_from_idx(handle, idx):
    return get_param_from_idx(handle, idx)["value"]


def get_param_value_from_idxs(handle, *idxs):
    return [p["value"] for p in get_param_from_idxs(handle, *idxs)]


def get_param(handle, param_info):
    shape, size, dtype = param_info["shape"], param_info["size"], param_info["dtype"]
    value = numpy.empty(shape, dtype="double", order="F")
    buff = ffi.cast("double *", value.ctypes.data)
    _error(xpc.xPCGetParam(handle, param_info["idx"], buff))
    value = value.astype(dtype)
    if size == 1:
        value = numpy.asscalar(value)
    return dict(param_info, value=value)


def get_param_value(handle, param_info):
    return get_param(handle, param_info)["value"]


def get_params(handle):
    return [get_param_from_idx(handle, i) for i in range(get_num_params(handle))]


def set_param_value_from_name(handle, block, name, value):
    idx = get_param_idx(handle, block, name)
    return set_param_value_from_idx(handle, idx, value)


def set_param_value_from_idx(handle, idx, value):
    param_info = get_param_info(handle, idx)
    return set_param_value(handle, param_info, value)


def set_param_value(handle, param_info, value):
    shape, size, dtype = param_info["shape"], param_info["size"], param_info["dtype"]
    value = numpy.array(value, dtype="double", copy=False, order="F")
    value.shape = shape
    assert value.size == size, "size mismatch"
    buff = ffi.cast("double *", value.ctypes.data)
    _error(xpc.xPCSetParam(handle, param_info["idx"], buff))


# Signals

"""
def get_num_signals(handle):
    return xpc.xPCGetNumSignals(handle)
"""


def get_signal_name(handle, idx):
    name = ffi.new("char[256]")
    _error(xpc.xPCGetSignalName(handle, idx, name))
    return ffi.string(name).decode()


def get_signal_idx(handle, name):
    return _error(xpc.xPCGetSignalIdx(handle, _to_bytes(name)))


def get_signal_info(handle, idx):
    full_name = get_signal_name(handle, idx)
    if "/" in full_name:
        block, name = full_name.rsplit("/", 1)
    else:
        block, name = "", full_name
    result = dict(block=block, name=name, idx=idx, shape=(), dtype=u"double", size=1)
    return result


def get_signal_infos(handle):
    return [get_signal_info(handle, i) for i in range(get_num_signals(handle))]


def get_signal_value_from_idx(handle, idx):
    return _error(xpc.xPCGetSignal(handle, idx))


def get_signal_value_from_idxs(handle, idxs=None):
    if idxs is None:
        idxs = tuple(range(get_num_signals(handle)))
    n = len(idxs)
    values = numpy.empty(n, order="F")
    buff = ffi.cast("double *", values.ctypes.data)
    _error(xpc.xPCGetSignals(handle, n, idxs, buff))
    return values


def get_signal_value_from_name(handle, block, name):
    full_name = block + "/" + name if block else name
    return get_signal_value_from_idx(handle, get_signal_idx(handle, full_name))


def get_signal_value_from_names(handle, *block_names):
    return [
        get_signal_value_from_name(handle, block, name) for block, name in block_names
    ]


# Scopes


def get_scope_list(handle):
    n_scopes = get_num_scopes(handle)
    buff = ffi.new("int[{}]".format(n_scopes))
    _error(xpc.xPCGetScopeList(handle, buff))
    return list(buff)


def _struct_to_dict(structure):
    return {n: getattr(structure, n) for n in dir(structure)}


def get_scope(handle, scope_idx):
    sd = _error(xpc.xPCGetScope(handle, scope_idx))
    result = _struct_to_dict(sd)
    signals = []
    for s in result["signals"]:
        if s == -1:
            break
        signals.append(s)
    result["signals"] = signals
    return result


def set_scope(handle, scope_dict):
    raise NotImplementedError


## Scope Signals


def sc_get_signals(handle, scope_id):
    nb_signals = sc_get_num_signals(handle, scope_id)
    buff = ffi.new("int[{}]".format(nb_signals))
    _error(xpc.xPCScGetSignals(handle, scope_id, buff))
    return list(buff)


def sc_get_data(
    handle, scope_id, signal_id, first_point=0, num_points=None, decimation=1
):
    if num_points is None:
        num_points = sc_get_num_samples(handle, scope_id) - first_point
    values = numpy.empty(num_points, order="F")
    buff = ffi.cast("double *", values.ctypes.data)
    _error(
        xpc.xPCScGetData(
            handle, scope_id, signal_id, first_point, num_points, decimation, buff
        )
    )
    return values


# Target scope


def tg_sc_get_grid(handle, scope_id):
    return True if _error(xpc.xPCTgScGetGrid(handle, scope_id)) else False


def tg_sc_set_auto_restart(handle, scope_id, grid):
    return _error(xpc.xPCTgScSetGrid(handle, scope_id, 1 if grid else False))


# missing tg_sc_get_y_limits, set_y_limits
# missing tg_sc_get_signal_format, tg_sc_set_signal_format

# Main


def main(argv=None):
    if argv is None:
        from sys import argv
    url = argv[1]
    host, port = url.rsplit(":", 1) if ":" in url else (url, "22222")
    return tcp_connect(host, port)


if __name__ == "__main__":
    simulink = main()
