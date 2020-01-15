# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import re
import gc
import psutil
from greenlet import greenlet
from contextlib import contextmanager


def file_descriptors(pid=None):
    """
    All file descriptors of a process

    :param int pid: current by default
    :returns dict:
    """
    if pid is None:
        pid = os.getpid()
    fdpath = os.path.join(psutil.PROCFS_PATH, str(pid), "fd")
    fds = {}
    for fd in os.listdir(fdpath):
        try:
            dest = os.readlink(os.path.join(fdpath, fd))
        except Exception:
            pass
        else:
            fds[int(fd)] = dest
    return fds


def greenlets():
    """
    All greenlets of this process

    :returns set:
    """
    return {obj for obj in gc.get_objects() if isinstance(obj, greenlet)}


def threads(pid=None):
    """
    All threads of a process

    :param int pid: current by default
    :returns list:
    """
    process = psutil.Process(pid=pid)
    return process.threads()


def memory(pid=None):
    """
    Used memory of a process

    :param int pid: current by default
    :returns int: bytes
    """
    process = psutil.Process(pid=pid)
    return process.memory_info().rss


def file_processes(pattern):
    """
    All processes that have a file opened

    Example: all open hdf5 files

    .. code-block:: python
        file_processes(r".+\.h5$")

    :param str pattern: regex pattern
    :returns list((str, Process)):
    """
    ret = []
    for proc in psutil.process_iter():
        try:
            fds = file_descriptors(proc.pid)
            for filename in fds.values():
                if re.match(pattern, filename):
                    ret.append((filename, proc))
        except Exception:
            pass
    return ret


def log_file_processes(logfunc, pattern):
    """
    All processes that have a file opened

    :param callable logfunc:
    :param str pattern: regex pattern
    """
    procs = file_processes(pattern)
    if not procs:
        return
    pid = os.getpid()
    msg = "\n### Files matching {} opened by {} process".format(
        repr(pattern), len(procs)
    )
    for fname, proc in procs:
        cmdline = repr(" ".join(proc.cmdline()))
        if proc.pid == pid:
            proc = "CURRENT {}".format(proc)
        msg += "\nFile {}:\n Opened by {}\n {}".format(repr(fname), proc, cmdline)
    msg += "\n###\n"
    logfunc(msg)


def matching_processes(pattern):
    """
    Find processes

    :param str pattern: regex pattern
    :yields Process:
    """
    for proc in psutil.process_iter():
        if re.match(pattern, " ".join(proc.cmdline())):
            yield proc


def terminate(pattern, wait=False):
    """
    Terminate a process

    :param str pattern: regex pattern
    :param bool force:
    """
    for proc in matching_processes(pattern):
        proc.terminate()
        if wait:
            proc.wait()


def kill(pattern, wait=False):
    """
    Terminate a process

    :param str pattern: regex pattern
    :param bool force:
    """
    for proc in matching_processes(pattern):
        proc.kill()
        if wait:
            proc.wait()


def log_fd_diff(logfunc, old_fds, prefix=""):
    """
    Print new file descriptors

    :param callable logfunc:
    :param dict old_fds:
    :param str prefix:
    """
    new_fds = file_descriptors()
    diff = set(new_fds.values()) - set(old_fds.values())
    if diff:
        if prefix:
            prefix = prefix.format(len(diff)) + ": "
        else:
            prefix = "{} fds difference".format(len(diff))
        logfunc("{}{}".format(prefix, list(sorted(diff))))
    return new_fds


def _fd_diff_exception(*args, **kwargs):
    raise RuntimeError(*args, **kwargs)


def raise_fd_diff(old_fds, prefix=""):
    """
    Raise exception when new file descriptors

    :param dict old_fds:
    :param str prefix:
    """
    return log_fd_diff(_fd_diff_exception, old_fds, prefix=prefix)


@contextmanager
def fd_leak_ctx(logfunc, prefix=""):
    """
    Print new file descriptors created within the context

    :param callable logfunc:
    :param str prefix:
    """
    old_fds = file_descriptors()
    try:
        yield
    finally:
        log_fd_diff(logfunc, old_fds, prefix=prefix)
