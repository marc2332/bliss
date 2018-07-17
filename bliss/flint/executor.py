"""Provide helpers to communicate with a Qt loop."""

# Import

import sys
import functools
import gevent
import gevent.event
import gevent.queue

from silx.gui import qt
from concurrent.futures import Future

# Global

__all__ = ['submit_to_qt_application', 'qt_safe',
           'connect_to_qt_signal', 'disconnect_from_qt_signal',
           'create_queue_from_qt_signal', 'disconnect_queue_from_qt_signal']

EXECUTOR = None


# Executor class

class QtExecutor(qt.QObject):

    _submit = qt.Signal(Future, object, tuple, dict)

    def __init__(self):
        super(QtExecutor, self).__init__(parent=None)
        # Makes sure the executor lives in the main thread
        app = qt.QApplication.instance()
        assert app is not None
        self.main_thread = app.thread()
        if self.thread() != self.main_thread:
            self.moveToThread(self.main_thread)
        # Connect signals
        self._submit.connect(self._run)

    @property
    def safe(self):
        return self.main_thread is self.main_thread.currentThread()

    def submit(self, fn, *args, **kwargs):
        future = Future()
        self._submit.emit(future, fn, args, kwargs)
        return future

    def _run(self, future, fn, args, kwargs):
        if not future.set_running_or_notify_cancel():
            return
        try:
            result = fn(*args, **kwargs)
        except BaseException:
            # Forward the traceback
            _, exc, tb = sys.exc_info()
            future.set_exception_info(exc, tb)
        else:
            future.set_result(result)


# Concurrent helper

def concurrent_to_gevent(future):
    asyncresult = gevent.event.AsyncResult()
    watcher = gevent.get_hub().loop.async()

    def gevent_callback():
        try:
            result = future.result()
        except BaseException as exc:
            # Forward the traceback
            info = sys.exc_info()
            asyncresult.set_exception(exc, info)
        else:
            asyncresult.set(result)
        finally:
            watcher.stop()

    watcher.start(gevent_callback)
    future.add_done_callback(lambda _: watcher.send())

    return asyncresult


# Exposed functions

def submit_to_qt_application(fn, *args, **kwargs):
    """Submit a task to safely run in the qt loop
    and return the task result.
    """
    global EXECUTOR
    # Lazy loading
    if EXECUTOR is None:
        EXECUTOR = QtExecutor()
    # Syncronous shortcut
    if EXECUTOR.safe:
        return fn(*args, **kwargs)
    future = EXECUTOR.submit(fn, *args, **kwargs)

    return concurrent_to_gevent(future).get()


def connect_to_qt_signal(signal, callback):
    """Connect to a given qt signal.

    The callback safely runs in the current gevent loop.
    """
    watcher = gevent.get_hub().loop.async()

    def slot(*args):
        watcher.start(callback, *args)
        watcher.send()

    callback._qt_slot = slot
    submit_to_qt_application(signal.connect, slot)


def disconnect_from_qt_signal(signal, callback):
    """Disconnect from the given qt signal."""
    slot = callback._qt_slot
    submit_to_qt_application(signal.disconnect, slot)


def create_queue_from_qt_signal(signal, maxsize=None):
    """Return a queue accumulating the emitted arguments
    of the given qt signal.
    """
    queue = gevent.queue.Queue(maxsize=maxsize)

    def callback(*args):
        queue.put(args)

    queue._qt_args = signal, callback
    connect_to_qt_signal(*queue._qt_args)
    return queue


def disconnect_queue_from_qt_signal(queue):
    """Disconnect the given queue from its qt signal
    and interrupt the iterating process.
    """
    disconnect_from_qt_signal(*queue._qt_args)
    queue.put(StopIteration)


def qt_safe(func):
    """Use a decorator to make a function qt safe"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return submit_to_qt_application(func, *args, **kwargs)
    return wrapper
