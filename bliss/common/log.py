from logging import ERROR, INFO, DEBUG, NOTSET
from logging import getLevelName
from traceback import extract_stack as tb_extract_stack
import sys


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

    if level < _log_level:
        return
    level_name = getLevelName(level)
    output = "%s: %s\n" % (level_name, msg)
    if level >= ERROR:
        sys.stderr.write(output)
    else:
        sys.stdout.write(output)


def error(error_msg, raise_exception=True, exception=RuntimeError):
    """Handle error messages, by default an exception is also raised"""
    try:
        return log(ERROR, error_msg)
    finally:
        if raise_exception:
            raise exception(error_msg)


def info(info_msg):
    """Handle info messages"""
    return log(INFO, info_msg)


def debug(debug_msg):
    """Handle debug messages and add them calling information"""
    filename, lineno, func_name, _ = _caller()
    msg = "%s ('%s`, line %d): %s" % (func_name, filename, lineno, debug_msg)
    return log(DEBUG, msg)
