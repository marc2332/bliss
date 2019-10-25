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

import gevent
from gevent import signal
import gevent.lock
from contextlib import contextmanager, ExitStack


def register_signal_handler(signalnum, handler):
    """
    :param int signalnum:
    :param callable handler:
    """
    oldhandler = signal.getsignal(signalnum)

    def newhandler(*args):
        try:
            handler()
        finally:
            gevent.signal(signalnum, oldhandler)

    gevent.signal(signalnum, newhandler)


def kill_on_exit(greenlet):
    """
    Make sure greenlet is killed in SIGQUIT and SIGINT

    :param Greenlet greenlet:
    """
    for signalnum in signal.SIGQUIT, signal.SIGINT:
        register_signal_handler(signalnum, greenlet.kill)


class SharedLockPool(object):
    """
    Allows to acquire locks identified by name recursively.
    """

    def __init__(self):
        self.__locks = {}
        self.__locks_mutex = gevent.lock.Semaphore(value=1)

    @contextmanager
    def _locks(self):
        self.__locks_mutex.acquire()
        try:
            yield self.__locks
        finally:
            self.__locks_mutex.release()

    def pop(self, name):
        with self._locks() as locks:
            return locks.pop(name, None)

    @contextmanager
    def acquire(self, name):
        with self._locks() as locks:
            lock = locks.get(name, None)
            if lock is None:
                locks[name] = lock = gevent.lock.RLock()
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    @contextmanager
    def acquire_context_creation(self, name, contextmngr, *args, **kwargs):
        """
        Acquire lock only during context creation.

        This can be used for example to protect the opening of a file
        but not hold the lock while the file is open.
        """
        with ExitStack() as stack:
            with self.acquire(name):
                ret = stack.enter_context(contextmngr(*args, **kwargs))
            yield ret
