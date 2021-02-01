# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Watchdog manager to record and log data, or kill the application
"""

from __future__ import annotations

import sys
import logging
import tracemalloc
import traceback
import os
import time
import psutil
import gevent

from silx.gui import qt

_logger = logging.getLogger(__name__)


def log_threads_traceback():
    """Print the current backtrace of all process into the current logger"""

    log = []
    log += ["---------- %s ----------" % "threads traceback"]
    for threadId, stack in sys._current_frames().items():
        log += ["ThreadID: %s" % threadId]
        for filename, lineno, name, line in traceback.extract_stack(stack):
            log += ['  File: "%s", line %d, in %s' % (filename, lineno, name)]
            if line:
                log += ["    %s" % line.strip()]

    log += [""]
    lines = "\n".join(log)
    _logger.info("%s", lines)


def log_greenlets_traceback():
    """Print the current start of all the greenlets"""
    log = []
    log += ["---------- %s ----------" % "greenlet traceback"]
    log += gevent.util.format_run_info()
    lines = "\n".join(log)
    _logger.info("%s", lines)


def log_memory_usage(previous_snapshot=None):
    """Print the current usage of the memory allocation"""
    if not tracemalloc.is_tracing():
        tracemalloc.start()

    if previous_snapshot is not None:
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(previous_snapshot, "lineno")
    else:
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

    log = []
    log += ["---------- %s ----------" % "tracemalloc"]
    for stat in top_stats[:40]:
        log += ["%s" % stat]
    log += [""]

    lines = "\n".join(log)
    _logger.info("%s", lines)


class _WatchDog:
    def initMonitoring(self):
        """Start monitoring the resources"""
        _logger.info("Start monitoring")
        tracemalloc.start()
        self._snapshot1 = tracemalloc.take_snapshot()

    def logMonitoring(self):
        """Display monitoring result and try to close"""
        _logger.info("Log monitoring")
        log_memory_usage(self._snapshot1)

    def logStack(self):
        log_threads_traceback()
        log_greenlets_traceback()

    def close(self):
        """Try to close the application"""
        _logger.info("Try to close the application")
        qt.QApplication.instance().exit()

    def kill(self):
        """Force to kill the process itself"""
        _logger.info("Send kill9")
        os.kill(os.getpid(), 9)


class MemoryStateWatchDog(_WatchDog):
    """
    A process to monitor the memory from a trigger.

    See `triggered`.
    """

    def __init__(self):
        self.__next = 0

    def triggered(self, signum, frame):
        """Trigger monitoring

        The first call will start monitoring, the second will log info.
        Extra calls log the memory from the initialization (not from the
        previous log).
        """
        _logger.info("Interrupted by %s", signum)
        if self.__next == 0:
            self.initMonitoring()
            self.__next = 1
        elif self.__next == 1:
            self.logMonitoring()
            self.__next = 1


class StackStateWatchDog(_WatchDog):
    """
    A process to catch a screenshot of the state of the execution.

    See `triggered`.
    """

    class _Thread(qt.QThread):
        def __init__(self, parent=None, callback=None):
            qt.QThread.__init__(self, parent=parent)
            self._running = True
            self._callback = callback

        def run(self):
            self._callback()

    def __init__(self):
        self.__thread = None

    def triggered(self, signum, frame):
        """Trigger screenshot of the execution stacks

        This creates a thread to log the execution state outside of the
        execution itself.
        """
        _logger.info("Interrupted by %s", signum)
        self.__thread = self._Thread(callback=self.logStack)
        self.__thread.start()


class MemoryWatchDog(_WatchDog):
    """
    A process to monitor the memory.

    When the process hit more than a percentage of the system an action
    is executed:

    - 50%: Start monitoring the memory
    - 60%: Log memory and execution stack and try to close Flint
    - 70%: Kill flint
    """

    class _Thread(qt.QThread):
        def __init__(self, parent=None, callback=None):
            qt.QThread.__init__(self, parent=parent)
            self._running = True
            self._callback = callback

        def stop(self):
            self._running = False

        def run(self):
            while self._running:
                time.sleep(10)
                self._callback()

    def __init__(self):
        self._thread = None
        self.__next = 0

    def start(self):
        if self._thread is not None:
            return
        thread = self._Thread(callback=self.__check)
        thread.start()
        self._thread = thread

    def stop(self):
        if self._thread is None:
            return
        self._thread.stop()
        self._thread.join()
        self._thread = None

    def __check(self):
        process = psutil.Process(os.getpid())
        mem = process.memory_percent()
        if mem > 50:
            if self.__next == 0:
                self.logStack()
                self.initMonitoring()
                self.__next = 1
        elif mem > 60:
            if self.__next == 1:
                self.logStack()
                self.logMonitoring()
                self.close()
                self.__next = 2
        elif mem > 70:
            if self.__next == 2:
                self.kill()
