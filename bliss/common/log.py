from logging import ERROR, INFO, DEBUG
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


def log(level, msg):
    level_name = getLevelName(level)
    output = "%5s: %s\n" % (level_name, msg)
    if level >= ERROR:
        sys.stderr.write(output)
    else:
        sys.stdout.write(output)


def error(error_msg, raise_exception=True, exception=RuntimeError):
    try:
        return log(ERROR, error_msg)
    finally:
        if raise_exception:
            raise exception(error_msg)


def info(info_msg):
    return log(INFO, info_msg)


def debug(debug_msg):
    filename, lineno, func_name, _ = _caller()
    msg = "%s ('%s`, line %d): %s" % (func_name, filename, lineno, debug_msg)
    return log(DEBUG, msg)
