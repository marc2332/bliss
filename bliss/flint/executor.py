"""Provide helpers to communicate with a Qt loop."""

# Import

import gevent.event
import gevent.queue

from silx.gui import qt
from concurrent.futures import Future

# Global

__all__ = ['submit_to_qt_application',
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
        mainThread = app.thread()
        if self.thread() != mainThread:
            self.moveToThread(mainThread)
        # Connect signals
        self._submit.connect(self._run)

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
    watcher = asyncresult.hub.loop.async()

    def callback(_):
        try:
            result = future.result()
        except BaseException as e:
            asyncresult.set_exception(e)
        else:
            asyncresult.set(result)
        finally:
            watcher.send()

    future.add_done_callback(callback)
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
    future = EXECUTOR.submit(fn, *args, **kwargs)
    # Hack: add a timeout so gevent doesn't freak out
    return concurrent_to_gevent(future).get(timeout=float('inf'))


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
