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
from gevent import monkey
from gevent import signal
import gevent.lock
from contextlib import contextmanager, ExitStack
from . import logging_utils


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


def log_gevent():
    gevent.get_hub().exception_stream = logging_utils.err_stream


def blocking_call(duration=3, logger=None):
    """
    Block the gevent's event loop
    """
    try:
        func = monkey.saved["time"]["sleep"]
        msg = "sleep was patched"
    except AttributeError:
        from time import sleep as func

        msg = "sleep was not patched not patched"
    msg = "Block event loop for {} sec ({})".format(duration, msg)
    if logger:
        logger.error(msg)
    else:
        logging_utils.print_err(msg)
    func(duration)


def start_heartbeat(logger, interval=1):
    """
    This spawns a heartbeat greenlet (for testing)

    :param logger:
    :param num interval:
    """

    class hartbeat(gevent.Greenlet):
        def _run(self):
            try:
                from itertools import count

                c = count()
                while True:
                    if gevent.config.monitor_thread:
                        suffix = "monitored"
                    else:
                        suffix = "not monitored"
                    msg = "heartbeat{} ({})".format(next(c), suffix)
                    logger.info(msg)
                    logger.error(msg)
                    gevent.sleep(interval)
            except gevent.GreenletExit:
                logger.info("heartbeat exits")

    greenlet = hartbeat()
    kill_on_exit(greenlet)
    greenlet.start()
    return greenlet


@contextmanager
def monitor_gevent():
    # Or use environment variable GEVENT_MONITOR_THREAD_ENABLE=true
    # Look in stderr for "appears to be blocked"
    gevent.config.monitor_thread = True
    hub = gevent.get_hub()
    hub.start_periodic_monitoring_thread()
    try:
        yield
    finally:
        hub.periodic_monitoring_thread.kill()


def greenlet_ident(g=None):
    if g is None:
        g = gevent.getcurrent()
    try:
        return g.minimal_ident
    except AttributeError:
        return gevent.get_hub().ident_registry.get_ident(g)


class SharedLockPool(object):
    """
    Allows to acquire locks identified by name recursively.
    """

    def __init__(self):
        self.__locks = {}
        self.__locks_mutex = gevent.lock.Semaphore(value=1)

    def __len__(self):
        return len(self.__locks)

    @property
    def names(self):
        return list(self.__locks.keys())

    @contextmanager
    def _modify_locks(self):
        self.__locks_mutex.acquire()
        try:
            yield self.__locks
        finally:
            self.__locks_mutex.release()

    @contextmanager
    def acquire(self, name):
        with self._modify_locks() as locks:
            lock = locks.get(name, None)
            if lock is None:
                locks[name] = lock = gevent.lock.RLock()
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._modify_locks() as locks:
                if not lock._count:
                    locks.pop(name)

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
