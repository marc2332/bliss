import os
import ctypes
from ctypes.util import find_library
from ctypes import CDLL, POINTER, byref, create_string_buffer
from ctypes import c_short, c_int, c_long, c_void_p, c_char_p

lib = CDLL(find_library("gpib") or "libgpib.so")
lib.ThreadIbsta.restype = c_int
lib.ThreadIberr.restype = c_int
lib.ThreadIbcnt.restype = c_int
lib.ThreadIbcnt.restype = c_long
lib.ibfind.argtypes = [c_char_p]
lib.ibfind.restype = c_int
lib.ibdev.argtypes = 6 * [c_int]
lib.ibdev.restype = c_int
lib.ibrd.argtypes = [c_int, c_void_p, c_long]
lib.ibrd.restype = c_int
lib.ibwrt.argtypes = [c_int, c_void_p, c_long]
lib.ibwrt.restype = c_int
lib.ibtmo.argtypes = [c_int, c_int]
lib.ibtmo.restype = c_int
lib.ibvers.argtypes = [POINTER(c_char_p)]
lib.gpib_error_string.argtypes = [c_int]
lib.gpib_error_string.restype = c_char_p

lib.ibln.argtypes = [c_int, c_int, c_int, POINTER(c_short)]
lib.ibln.restype = c_int

NO_SAD = 0
ALL_SAD = -1

EDVR = 0
EFSO = 12
ERR = 15


class GPIBError(Exception):
    pass


def error_message(fname=None, code=None):
    code = lib.ThreadIberr() if code is None else code
    msg = ""
    if fname:
        msg += fname + "() "
    msg += "error: " + lib.gpib_error_string(code)
    if code in (EDVR, EFSO):
        errno = lib.ThreadIbcntl()
        if errno == 0:
            errno = ctypes.get_errno()
        if errno == 0:
            # weird, Iberr says it is a syst. call error but ibcntl
            # does not seem to have an error code.
            msg += ": {0}??? ({1})".format(os.strerror(errno), errno)
        else:
            msg += ": {0} ({1})".format(os.strerror(errno), errno)
    return msg


def _handle_error(err, fname=None):
    if err & ERR:
        raise GPIBError(error_message(fname))
    return err


def ibdev(board_index, pad, sad=0, tmo=11, send_eoi=1, eos=0):
    r = lib.ibdev(board_index, pad, sad, tmo, send_eoi, eos)
    if r < 0:
        raise GPIBError(error_message("ibdev"))
    return r


def ibrd(ud, size):
    buff = create_string_buffer(size)
    err = lib.ibrd(ud, buff, size)
    _handle_error(err, "ibrd")
    return buff[: lib.ThreadIbcntl()]


def ibwrt(ud, buff):
    return _handle_error(lib.ibwrt(ud, buff, len(buff)), "ibwrt")


def ibtmo(ud, tmo):
    return _handle_error(lib.ibtmo(ud, tmo), "ibtmo")


def ibln(ud, pad, sad=ALL_SAD):
    r = c_short(-999)
    _handle_error(lib.ibln(ud, pad, sad, byref(r)), "ibln")
    return r


def ibvers():
    data = c_char_p()
    lib.ibvers(byref(data))
    return data.value
