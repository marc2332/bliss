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

__all__ = ["submit_to_qt_application", "qt_safe", "QtSignalQueue"]

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
    watcher = gevent.get_hub().loop.async_()

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


def qt_safe(func):
    """Use a decorator to make a function qt safe"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return submit_to_qt_application(func, *args, **kwargs)

    return wrapper


# Qt signal gevent queue


class QtSignalQueue(gevent.queue.Queue):
    """A queue accumulating the emitted arguments of the provided qt signal."""

    def __init__(self, signal, maxsize=None):
        super(QtSignalQueue, self).__init__(maxsize=maxsize)
        self._qt_signal = signal
        self._qt_watcher = gevent.get_hub().loop.async_()
        submit_to_qt_application(signal.connect, self._qt_slot)

    def _qt_slot(self, *args):
        self._qt_watcher.start(lambda: self.put_nowait(args))
        self._qt_watcher.send()

    def disconnect(self):
        """Disconnect the given queue from its qt signal
        and interrupt the iterating process.
        """
        if self._qt_signal is None:
            return
        submit_to_qt_application(self._qt_signal.disconnect, self._qt_slot)
        self._qt_watcher.stop()
        self._qt_signal = None
        self.put(StopIteration)
