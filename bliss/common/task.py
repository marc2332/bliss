# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import errno
import types
import gevent
import signal
import functools
 
class TaskException:

    def __init__(self, exc_type, exception, tb):
        self.exc_type = exc_type
        self.exception = exception
        self.tb = tb


class wrap_errors(object):

    def __init__(self, func, started_event):
        """Make a new function from `func', such that it catches all exceptions
        and return it as a TaskException object
        """
        self.func = func
        self.started_event = started_event

    def __call__(self, *args, **kwargs):
        func = self.func
        if self.started_event:
            self.started_event.set()
        try:
            return func(*args, **kwargs)
        except:
            return TaskException(*sys.exc_info())

    def __str__(self):
        return str(self.func)

    def __repr__(self):
        return repr(self.func)

    def __getattr__(self, item):
        return getattr(self.func, item)


def special_get(self, *args, **kwargs):
    ret = self._get(*args, **kwargs)
    
    if isinstance(ret, TaskException):
        raise ret.exc_type, ret.exception, ret.tb
    else:
        return ret


def task(func):
    @functools.wraps(func)
    def start_task(*args, **kwargs):
        wait = kwargs.pop("wait", True)
        timeout = kwargs.pop("timeout", None)
        wait_started = kwargs.pop("wait_started", None)

        started_event = gevent.event.Event() if wait_started else None
        t = gevent.spawn(wrap_errors(func, started_event), *args, **kwargs)
        t._get = t.get
        setattr(t, "get", types.MethodType(special_get, t))

        if wait_started:
            try:
                started_event.wait()
            except:
                t.kill()

        if not wait:
            return t

        try:
            return t.get(timeout=timeout)
        except:
            # kill task in case of timeout, for example
            t.kill()
            raise

    return start_task

