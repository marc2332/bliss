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
import logging
import gevent
from gevent import monkey
from gevent import signal
from gevent import hub
import gevent.lock
from contextlib import contextmanager, ExitStack
from . import logging_utils


_logger = logging.getLogger(__name__)


def register_signal_handler(signalnum, handler, *args, **kw):
    """
    :param int signalnum:
    :param callable handler:
    :param *args: for `handler`
    :param **kw: for `handler`
    """

    def wrapper():
        try:
            handler(*args, **kw)
        finally:
            watcher.cancel()
            os.kill(os.getpid(), signalnum)

    watcher = hub.signal(signalnum, wrapper)
    return watcher


@contextmanager
def kill_on_exit(timeout=3):
    """Within this context SIGQUIT, SIGINT and SIGTERM trigger
    killing the current greenlet. This can be used if explicit
    finalization is required in a greenlet.

    :param num timeout: for `Greenlet.kill`
    """
    handler = gevent.getcurrent().kill
    watchers = [
        register_signal_handler(signalnum, handler, timeout=timeout)
        for signalnum in (signal.SIGQUIT, signal.SIGINT, signal.SIGTERM)
    ]
    try:
        yield
    finally:
        for w in watchers:
            try:
                w.cancel()
            except Exception as e:
                _logger.error(f"Exception during kill_on_exit cleanup: {e}")


def log_gevent():
    """
    Redirect gevent exception stream to error stream
    """
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

    class heartbeat(gevent.Greenlet):
        def _run(self):
            kill_on_exit()
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

    return heartbeat.spawn()


@contextmanager
def monitor_gevent():
    """
    Report for blocking operations.

    Or use environment variable GEVENT_MONITOR_THREAD_ENABLE=true
    Look in stderr for "appears to be blocked"
    """
    gevent.config.monitor_thread = True
    hub = gevent.get_hub()
    hub.start_periodic_monitoring_thread()
    try:
        yield
    finally:
        hub.periodic_monitoring_thread.kill()


def greenlet_ident(g=None):
    """
    :returns int:
    """
    if g is None:
        g = gevent.getcurrent()
    try:
        return g.minimal_ident
    except AttributeError:
        return gevent.get_hub().ident_registry.get_ident(g)


class SharedLockPool:
    """
    Allows to acquire locks identified by name (hashable type) recursively.
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
