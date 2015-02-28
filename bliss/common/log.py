from logging import ERROR, INFO, DEBUG, NOTSET
from logging import getLevelName
from traceback import extract_stack as tb_extract_stack
import sys
import time

# this is to make flake8 happy
NOTSET
###


class bcolors:
    PINK = '\033[95m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    ENDC = '\033[0m'


# LOG LEVELS :
#      eMotion   |     IcePAP     |  Tango
# ------------------------------------------
#   NOTSET ==  0 | 0 == DBG_NONE  | OFF
#   DEBUG  == 10 | 4 == DBG_DATA  | DEBUG
#   INFO   == 20 | 2 == DBG_TRACE | INFO
#   WARNING== 30 |                | WARN
#   ERROR  == 40 | 1 == DBG_ERROR | ERROR
#   CRITIC == 50 |                | FATAL

# tango log levels :
# OFF:   Nothing is logged
# FATAL: A fatal error occurred. The process is about to abort
# ERROR: An (unrecoverable) error occurred but the process is still alive
# WARN:  An error occurred but could be recovered locally
# INFO:  Provides information on important actions performed
# DEBUG: Generates detailed info describing internal behavior of a device
#
# Levels are ordered the following way:
# DEBUG < INFO < WARN < ERROR < FATAL < OFF

time0 = time.time()


def _caller(up=1):
    """Return (file, line, func, text) of caller's caller"""
    try:
        f = tb_extract_stack(limit=up + 2)
        if f:
            return f[0]
    except:
        pass
    return ('', 0, '', None)


# By default only print errors
_log_level = ERROR


def level(level=None):
    """Change the current debug level and always return the current level"""
    global _log_level

    if level is not None:
        if level < 0:
            raise ValueError("Invalid new log level")
        _log_level = level

    return _log_level


def log(level, msg):
    """Handle log messages"""
    global _log_level

    if level == NOTSET or level < _log_level:
        return
    level_name = getLevelName(level)
    output = "%s: %s\n" % (level_name, msg)
    if level >= ERROR:
        error_output(output)
    else:
        log_output(output)


def error_output(msg):
    sys.stderr.write(msg)
    sys.stderr.flush()


def log_output(msg):
    sys.stdout.write(msg)
    sys.stdout.flush()


def error(error_msg, raise_exception=True, exception=RuntimeError):
    """Handle error messages, by default an exception is also raised"""
    try:
        return log(ERROR, error_msg)
    finally:
        if raise_exception:
            raise exception(error_msg)


def exception(error_msg, raise_exception=True):
    """Exception messages, showing full traceback"""
    exc_info = sys.exc_info()
    if exc_info == (None, None, None):
        return error(error_msg, raise_exception=raise_exception)
    log(ERROR, error_msg)
    sys.excepthook(*exc_info)
    if raise_exception:
        raise exc_info[0], exc_info[1], exc_info[2]


def info(info_msg):
    """Handle info messages"""
    return log(INFO, info_msg)


def debug(debug_msg):
    """Handle debug messages and add them calling information"""
    filename, lineno, func_name, _ = _caller()

    # Reduces displayed path : keeps 2 last fields of filename.
    path = filename.split("/")
    try:
        path = path[-2:]
    except:
        path = path

    short_filename = "%s" % "/".join(path)
    short_filename = bcolors.BLUE + short_filename + bcolors.ENDC
    debug_msg = bcolors.PINK + debug_msg + bcolors.ENDC
    msg = "%.3f %s() (%s, l.%d): %s" % (time.time() - time0, func_name, short_filename, lineno, debug_msg)

    ret = log(DEBUG, msg)
    return ret
