# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helpers to make TANGO_ & gevent_ work together"""

from gevent import _threading
import threading
import gevent.event
import sys
import atexit
import gevent
import functools

main_queue = _threading.Queue()
gevent_thread_lock = _threading.Lock()
gevent_thread_started = _threading.Event()
gevent_thread = None
GEVENT_THREAD_ID = None
read_event_watcher = None
objs = {}
stop_event = gevent.event.Event()

if not hasattr(gevent, "wait"):

    def gevent_wait(timeout=None):
        return gevent.run(timeout)

    gevent.wait = gevent_wait


class CallException:
    def __init__(self, exception, error_string, tb):
        self.exception = exception
        self.error_string = error_string
        self.tb = tb


def terminate_thread():
    if read_event_watcher:
        execute("exit")


atexit.register(terminate_thread)


def deal_with_job(req, args, kwargs):
    def run(req, fn, args, kwargs):
        try:
            result = fn(*args, **kwargs)
        except:
            exception, error_string, tb = sys.exc_info()
            result = CallException(exception, error_string, tb)

        req.set_result(result)

    if req.method == "new":
        klass = args[0]
        args = args[1:]
        try:
            new_obj = klass(*args, **kwargs)
        except:
            exception, error_string, tb = sys.exc_info()
            result = CallException(exception, error_string, tb)
            req.set_result(result)
            return

        queue = _threading.Queue()
        watcher = gevent.get_hub().loop.async_()
        watcher.start(functools.partial(read_from_queue, queue))
        objs[id(new_obj)] = {"queue": queue, "watcher": watcher, "obj": new_obj}

        req.set_result(new_obj)
    elif req.method == "exit":
        req.set_result(stop_event.set())
    elif callable(req.method):
        run(req, req.method, args, kwargs)
    else:
        obj = objs[req.obj_id]["obj"]
        try:
            prop = getattr(obj.__class__, req.method)
        except AttributeError:
            pass
        else:
            if isinstance(prop, property):
                if args:  # must be setter
                    run(req, prop.fset, [obj] + list(args), kwargs)
                else:
                    run(req, prop.fget, [obj], kwargs)
                return

        try:
            method = getattr(obj, req.method)
        except AttributeError:
            exception, error_string, tb = sys.exc_info()
            result = CallException(exception, error_string, tb)
            req.set_result(result)
        else:
            if callable(method):
                # method
                run(req, method, args, kwargs)
            else:
                # attribute
                if args:
                    # write
                    setattr(obj, req.method, args[0])
                    req.set_result(None)
                else:
                    # read
                    req.set_result(method)


def read_from_queue(queue):
    req, args, kwargs = queue.get()
    gevent.spawn(deal_with_job, req, args, kwargs)


def process_requests(main_queue):
    global GEVENT_THREAD_ID
    GEVENT_THREAD_ID = id(threading.current_thread())

    global read_event_watcher
    read_event_watcher = gevent.get_hub().loop.async_()
    read_event_watcher.start(functools.partial(read_from_queue, main_queue))

    gevent_thread_started.set()

    while not stop_event.is_set():
        gevent.wait(timeout=1)


class threadSafeRequest(object):
    def __init__(self, method, obj_id=None, queue=None, watcher=None):
        self.obj_id = obj_id
        self.method = method
        self.queue = queue or main_queue
        self.watcher = watcher or read_event_watcher
        self.done_event = _threading.Event()
        self.result = None

    def __call__(self, *args, **kwargs):
        if id(threading.current_thread()) != GEVENT_THREAD_ID:
            self.queue.put((self, args, kwargs))
            self.watcher.send()
            self.done_event.wait()
        else:
            deal_with_job(self, args, kwargs)
        result = self.result
        self.result = None
        self.done_event.clear()
        if isinstance(result, CallException):
            raise result.error_string.with_traceback(result.tb)
        return result

    def set_result(self, res):
        self.result = res
        self.done_event.set()


class objectProxy:
    @staticmethod
    def exit():
        threadSafeRequest("exit")()

    def __init__(self, obj):
        self.obj_id = id(obj)

    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        # to do: replace getattr by proper introspection
        # to make a real proxy
        try:
            queue = objs[self.obj_id]["queue"]
            watcher = objs[self.obj_id]["watcher"]
        except KeyError:
            queue = None
            watcher = None
        return threadSafeRequest(attr, self.obj_id, queue, watcher)

    def get_base_obj(self):
        d = objs.get(self.obj_id)
        if d:
            return d.get("obj")


def check_gevent_thread():
    global gevent_thread

    if gevent_thread is None:
        with gevent_thread_lock:
            gevent_thread = _threading.start_new_thread(process_requests, (main_queue,))

    gevent_thread_started.wait()


def execute(fn, *args, **kwargs):
    """Execute fn with args in a separate, dedicated gevent thread"""
    check_gevent_thread()

    req = threadSafeRequest(fn)
    return req(*args, **kwargs)


def get_proxy(object_class, *args, **kwargs):
    """Instanciate new object from given class in a separate,
       dedicated gevent thread"""
    check_gevent_thread()

    new_obj_request = threadSafeRequest("new")
    new_obj = new_obj_request(object_class, *args, **kwargs)
    proxy = objectProxy(new_obj)
    return proxy
