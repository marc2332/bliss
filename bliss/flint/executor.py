"""Provide helpers to communicate with a Qt loop."""

# Import

import gevent.event
import gevent.queue

from silx.gui import qt
from silx.third_party.concurrent_futures import Future

# Global

__all__ = ['submit_to_qt', 'connect_to_qt', 'disconnect_from_qt',
           'queue_from_qt_signal', 'disconnect_queue_from_qt']

EXECUTOR = None


# Executor class

class QtExecutor(qt.QObject):

    _submit = qt.Signal(Future, object, tuple, dict)

    def __init__(self):
        super(QtExecutor, self).__init__(parent=None)
        # Makes sure the executor lives in the main thread
        app = qt.QApplication.instance()
        assert app is not None
        mainThread = app.thread()
        if self.thread() != mainThread:
            self.moveToThread(mainThread)
        # Connect signals
        self._submit.connect(self._run)
        self._connect.connect(self._run_connect)

    def submit(self, fn, *args, **kwargs):
        future = Future()
        self._submit.emit(future, fn, args, kwargs)
        return future

    def _run(self, future, fn, args, kwargs):
        if not future.set_running_or_notify_cancel():
            return
        try:
            result = fn(*args, **kwargs)
        except BaseException as e:
            future.set_exception(e)
        else:
            future.set_result(result)


# Concurrent helper

def concurrent_to_gevent(future):
    asyncresult = gevent.event.AsyncResult()

    def callback(_):
        try:
            result = future.get()
        except BaseException as e:
            asyncresult.set_exception(e)
        else:
            asyncresult.set(result)
        finally:
            asyncresult.hub.loop.async().send()

    future.add_done_callback(callback)
    return asyncresult


# Exposed functions

def submit_to_qt(fn, *args, **kwargs):
    global EXECUTOR
    # Lazy loading
    if EXECUTOR is None:
        EXECUTOR = QtExecutor()
    future = EXECUTOR.submit(fn, *args, **kwargs)
    return concurrent_to_gevent(future).get()


def connect_to_qt(obj, callback):
    watcher = gevent.get_hub().loop.async()

    def slot(*args):
        watcher.start(callback, *args)
        watcher.send()

    callback._qt_slot = slot
    submit_to_qt(obj.connect, slot)


def disconnect_from_qt(obj, callback):
    slot = callback._qt_slot
    submit_to_qt(obj.disconnect, slot)


def queue_from_qt_signal(obj):
    queue = gevent.queue.Queue()

    def callback(*args):
        queue.put(args)

    queue._qt_args = obj, callback
    connect_to_qt(*queue._qt_args)
    return queue


def disconnect_queue_from_qt(queue):
    disconnect_from_qt(*queue._qt_args)
    queue.put(StopIteration)
