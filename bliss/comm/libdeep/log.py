# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
from traceback import extract_stack
from os.path import basename


# Verbose levels
DBG_NONE    = 0
DBG_ERROR   = 1
DBG_TRACE   = 2
DBG_DATA    = 4
DBG_ASYNC   = 0x10
DBG_ALL     = 0x1f


# By default only print errors
_log_level = DBG_ERROR


def log(level, msg):
    """Handle log messages"""
    global _log_level

    level_indent = _get_level_indent(level)
    output = "%s%s\n" % (level_indent, msg)
    if level >= DBG_ERROR:
        sys.stderr.write(output)
    else:
        sys.stdout.write(output)


def _get_level_indent(level):
    """Returns a string corresponding to the numerical level"""
    ret = "%*s"%((level&0x07)*4," ")
    if level&DBG_ASYNC:
        ret ="%20sASYNC:"%" "

    filename, lineno, func_name, txt = _caller()
    ret = ret + basename(filename).split('.')[0] + "." + func_name + ":"

    return ret


def _caller():
    """Returns (file, line, func, text) of caller's caller"""
    try:
        f = extract_stack(limit=5)
        if f:
            return f[0]
    except:
        pass
    return ('', 0, '', None)


def level(level=None):
    """Change the current debug level and always return the current level"""
    global _log_level
    
    if level is not None:
        if level < 0:
            raise ValueError("Invalid new log level")
        _log_level = level

    return _log_level


def error(error_msg, raise_exception=True, exception=RuntimeError):
    """Handle error messages, by default an exception is also raised"""

    if ((_log_level&0x07) < DBG_ERROR):
        return

    log(DBG_ERROR, error_msg)

    if raise_exception:
        raise exception(error_msg)


def trace(info_msg):
    """Handle trace messages"""

    if ((_log_level&0x07) < DBG_TRACE):
        return 
    log(DBG_TRACE, info_msg)


def data(info_msg):
    """Handle debug messages"""

    if ((_log_level&0x07) < DBG_DATA):
        return 
    log(DBG_DATA, info_msg)


def async(info_msg):
    """Handle messages about asynchronous reception"""

    if ((_log_level&DBG_ASYNC) == 0):
        return 

    log(DBG_ASYNC, info_msg)


