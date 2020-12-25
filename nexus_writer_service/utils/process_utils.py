# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import re
import gc
import psutil
from greenlet import greenlet
import threading
import gevent.socket
import socket
import pprint
import inspect
from contextlib import contextmanager
import functools


def _dictobj_replace(obj):
    if isinstance(obj, (str, bytes)):
        s = str(obj[:10])
        return s + "..."
    elif isinstance(obj, bytearray):
        s = str(obj[:10])
        return f"{(s[:-2])}...{(s[-2:])}"
    else:
        return obj


def print_obj(obj, indent=0):
    tab = " " * indent
    if inspect.ismodule(obj):
        print(f"{tab}+ {repr(obj)}")
    else:
        print(f"{tab}+ <{type(obj).__name__} object at 0x{'{:x}'.format(id(obj))}>")
        if isinstance(obj, dict):
            obj = {k: _dictobj_replace(v) for k, v in obj.items()}
        s = "".join(pprint.pformat(obj, indent=indent + 2, compact=True, depth=1))
        print(f"{tab}|_{s}")


def printobj_backref(queue, max_depth=10):
    ignore = set()
    ignore.add(id(ignore))
    ignore.add(id(queue))
    queue = [(obj, 0) for obj in queue]
    ignore.add(id(queue))
    for tpl in queue:
        ignore.add(id(tpl))
    gc.collect()
    while queue:
        target, depth = queue.pop()
        ignore.add(id(target))
        if depth > max_depth:
            continue
        print_obj(target, indent=depth)
        if inspect.ismodule(target):
            continue

        refs = gc.get_referrers(target)
        ignore.add(id(refs))
        for ref in refs:
            if id(ref) in ignore:
                continue
            tpl = (ref, depth + 2)
            ignore.add(id(tpl))
            queue.append(tpl)


def gc_collect(*classes):
    """
    :param classes:
    :returns set:
    """
    ret = []
    if not classes:
        return ret
    # TODO: gevent monitoring says this blocks
    # find a better way?
    for ob in gc.get_objects():
        gevent.sleep()
        try:
            if not isinstance(ob, classes):
                continue
        except ReferenceError:
            continue
        ret.append(ob)
    return ret


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
    return set(gc_collect(greenlet))


def sockets():
    """
    All sockets of this process

    :returns set:
    """
    return set(gc_collect(gevent.socket.socket, socket.socket))


def resources(*classes):
    """
    All other resource of this process

    :returns set:
    """
    return set(gc_collect(*classes))


def threads(pid=None):
    """
    All threads of a process

    :param int pid: current by default
    :returns set:
    """
    if pid is None or pid == os.getpid():
        return set(threading.enumerate())
    else:
        process = psutil.Process(pid=pid)
        return {t.id for t in process.threads()}


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


def log_diff(logfunc, difffunc, typ, diffargs=None, prefix=""):
    """
    :param callable logfunc:
    :param callable difffunc:
    :param str typ:
    :param tuple diffargs:
    :param str prefix:
    """
    new, diff = difffunc(*diffargs)
    if diff:
        if prefix:
            prefix = prefix.format(len(diff)) + ": "
        else:
            prefix = f"{len(diff)} {typ} difference "
        try:
            lst = sorted(diff)
        except TypeError:
            lst = list(diff)
        printobj_backref(lst)
        lst = list(map(str, lst))
        logfunc(f"{prefix}{lst}")
    return new


def _fd_diff(old):
    """New file descriptors

    :param dict old:
    :returns dict, set:
    """
    new = file_descriptors()
    diff = set(new.values()) - set(old.values())
    return new, diff


def _class_diff(old, classes):
    """New instance diff

    :param set old:
    :param tuple classes:
    :returns set, set:
    """
    new = set(gc_collect(*classes))
    return new, new - old


def _greenlet_diff(old):
    """
    New greenlets

    :param set old:
    :returns set, set:
    """
    new = greenlets()
    return new, new - old


def _socket_diff(old):
    """
    New sockets

    :param set old:
    :returns set, set:
    """
    new = sockets()
    return new, new - old


def _thread_diff(old):
    """
    New threads

    :param set old:
    :returns set, set:
    """
    new = threads()
    return new, new - old


def log_fd_diff(logfunc, old, prefix=""):
    """
    Print new file descriptors

    :param callable logfunc:
    :param dict old:
    :param str prefix:
    :returns dict:
    """
    return log_diff(logfunc, _fd_diff, "fds", diffargs=(old,), prefix=prefix)


def log_greenlet_diff(logfunc, old, prefix=""):
    """
    Print new greenlets

    :param callable logfunc:
    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_diff(
        logfunc, _greenlet_diff, "greenlets", diffargs=(old,), prefix=prefix
    )


def log_class_diff(logfunc, old, classes, prefix=""):
    """Print new class instances

    :param callable logfunc:
    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_diff(
        logfunc, _class_diff, str(classes), diffargs=(old, classes), prefix=prefix
    )


def log_socket_diff(logfunc, old, prefix=""):
    """
    Print new sockets

    :param callable logfunc:
    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_diff(logfunc, _socket_diff, "sockets", diffargs=(old,), prefix=prefix)


def log_thread_diff(logfunc, old, prefix=""):
    """
    Print new threads

    :param callable logfunc:
    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_diff(logfunc, _thread_diff, "threads", diffargs=(old,), prefix=prefix)


def _diff_exception(*args, **kwargs):
    raise AssertionError(*args, **kwargs)


def assert_fd_diff(old, prefix=""):
    """
    Raise exception when new file descriptors

    :param dict old:
    :param str prefix:
    :returns dict:
    """
    return log_fd_diff(_diff_exception, old, prefix=prefix)


def assert_greenlet_diff(old, prefix=""):
    """
    Raise exception when new greenlets

    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_greenlet_diff(_diff_exception, old, prefix=prefix)


def assert_class_diff(old, classes, prefix=""):
    """
    Raise exception when new instances

    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_class_diff(_diff_exception, old, classes, prefix=prefix)


def assert_socket_diff(old, prefix=""):
    """
    Raise exception when new sockets

    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_socket_diff(_diff_exception, old, prefix=prefix)


def assert_thread_diff(old, prefix=""):
    """
    Raise exception when new threads

    :param set old:
    :param str prefix:
    :returns set:
    """
    return log_thread_diff(_diff_exception, old, prefix=prefix)


class ResourceMonitor:
    def __init__(self, *classes, greenlets=True, threads=True, fds=True, sockets=True):
        self.classes = classes
        if classes:
            self.others = set()
        else:
            self.others = None
        if greenlets:
            self.greenlets = set()
        else:
            self.greenlets = None
        if threads:
            self.threads = set()
        else:
            self.threads = None
        if fds:
            self.fds = set()
        else:
            self.fds = None
        if sockets:
            self.sockets = set()
        else:
            self.sockets = None

    def start(self):
        gevent.get_hub()
        if self.greenlets is not None:
            self.greenlets = greenlets()
        if self.threads is not None:
            self.threads = threads()
        if self.fds is not None:
            self.fds = file_descriptors()
        if self.sockets is not None:
            self.sockets = sockets()
        if self.others is not None:
            self.others = resources(*self.classes)

    @contextmanager
    def check_leaks_context(self, msg=None):
        self.start()
        try:
            yield
        finally:
            self.check_leaks(msg=msg)

    def wait_gc_collect(self):
        gevent.sleep(0.1)
        while gc.collect():
            gevent.sleep(0.1)

    def check_leaks(self, msg=None):
        self.wait_gc_collect()
        if self.others is not None:
            assert_class_diff(self.others, self.classes, prefix=msg)
        if self.sockets is not None:
            assert_socket_diff(self.sockets, prefix=msg)
        if self.fds is not None:
            assert_fd_diff(self.fds, prefix=msg)
        if self.threads is not None:
            assert_thread_diff(self.threads, prefix=msg)
        if self.greenlets is not None:
            assert_greenlet_diff(self.greenlets, prefix=msg)


def gevent_thread_leak():
    # gevent issue #1601
    return tuple(map(int, gevent.__version__.split(".")[:3])) < (20, 5, 1)


def check_resource_leaks(*classes, **kw):
    """Decorator for function resource checking
    """

    def _check_resource_leaks(method):
        @functools.wraps(method)
        def inner(*args, **kwargs):
            mon = ResourceMonitor(*classes, **kw)
            with mon.check_leaks_context(msg=method.__name__):
                method(*args, **kwargs)

        return inner

    return _check_resource_leaks
