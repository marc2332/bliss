# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

__all__ = ["xpc", "ffi"]

import os
from cffi import FFI

ffi = FFI()

_this_dir = os.path.dirname(__file__)
_api_h_filename = os.path.join(_this_dir, "xpcapi.h")
_api_dll_filename = os.path.join(_this_dir, "xpcapi.dll")

with open(_api_h_filename, "r") as _api_h_file:
    _api_h_text = _api_h_file.read()

ffi.cdef(_api_h_text)

xpc = ffi.dlopen(_api_dll_filename)
