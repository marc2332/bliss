# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Common functionality (:mod:`~bliss.common.event`, :mod:`~bliss.common.log`, \
:mod:`~bliss.common.axis`, :mod:`~bliss.common.temperature`, etc)

This module gathers most common functionality to bliss (from
:mod:`~bliss.common.event` to :mod:`~bliss.common.axis`)

.. autosummary::
   :toctree:

   axis
   encoder
   event
   hook
   log
   measurement
   plot
   scans
   standard
   task_utils
   temperature
   utils
"""

import gevent
from .event import dispatcher


class Actuator:
    def __init__(self, set_in=None, set_out=None, is_in=None, is_out=None):
        self.__in = False
        self.__out = False
        if any((set_in, set_out, is_in, is_out)):
            self._set_in = set_in
            self._set_out = set_out
            self._is_in = is_in
            self._is_out = is_out

    def set_in(self, timeout=None):
        # this is to know which command was asked for,
        # in case we don't have a return (no 'self._is_in' or out)
        self.__in = True
        self.__out = False
        try:
            with gevent.Timeout(timeout):
                while True:
                    self._set_in()
                    if self.is_in():
                        break
                    else:
                        gevent.sleep(0.5)
        finally:
            dispatcher.send("state", self, self.state)

    def set_out(self, timeout=None):
        self.__out = True
        self.__in = False
        try:
            with gevent.Timeout(timeout):
                while True:
                    self._set_out()
                    if self.is_out():
                        break
                    else:
                        gevent.sleep(0.5)
        finally:
            dispatcher.send("state", self, self.state)

    def is_in(self):
        if self._is_in is not None:
            return self._is_in()
        else:
            if self._is_out is not None:
                return not self._is_out()
            else:
                return self.__in

    def is_out(self):
        if self._is_out is not None:
            return self._is_out()
        else:
            if self._is_in is not None:
                return not self._is_in()
            else:
                return self.__out

    @property
    def state(self):
        state = ""
        if self.is_in():
            state += "IN"
        if self.is_out():
            state += "OUT"
        if not state or state == "INOUT":
            return "UNKNOWN"
        return state


# to be remove in next release
from types import ModuleType


class task_utils(ModuleType):
    __all__ = [
        "cleanup",
        "error_cleanup",
        "task",
        "special_get",
        "TaskException",
        "wrap_errors",
    ]

    @staticmethod
    def cleanup(*args, **kwargs):
        import warnings
        from . import cleanup

        warnings.simplefilter("once")
        warnings.warn(
            "Use: module **bliss.common.cleanup** instead of task_utils module",
            DeprecationWarning,
        )
        return cleanup.cleanup(*args, **kwargs)

    @staticmethod
    def error_cleanup(*args, **kwargs):
        kwargs.setdefault("error_cleanup", True)
        return task_utils.cleanup(*args, **kwargs)

    @staticmethod
    def task(func):
        import warnings

        warnings.simplefilter("once")
        warnings.warn(
            "Use: module **bliss.common.task** instead of task_utils module",
            DeprecationWarning,
        )
        from . import task

        return task.task(func)

    @staticmethod
    def special_get(self, *args, **kwargs):
        import warnings

        warnings.simplefilter("once")
        from . import task

        warnings.warn(
            "Use: module **bliss.common.task** instead of task_utils module",
            DeprecationWarning,
        )
        return task.special_get(self, *args, **kwargs)

    @staticmethod
    def TaskException(*args, **kwargs):
        import warnings

        warnings.simplefilter("once")
        from . import task

        warnings.warn(
            "Use: module **bliss.common.task** instead of task_utils module",
            DeprecationWarning,
        )
        return task.TaskException(*args, **kwargs)

    @staticmethod
    def wrap_errors(*args, **kwargs):
        import warnings

        warnings.simplefilter("once")
        from . import task

        warnings.warn(
            "Use: module **bliss.common.task** instead of task_utils module",
            DeprecationWarning,
        )
        return task.wrap_errors(*args, **kwargs)


import sys

sys.modules[__name__ + ".task_utils"] = task_utils("task_utils")
# ENDOF to be removed
