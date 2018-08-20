"""Tests for the qt executor module."""

import Queue
import threading

import gevent
import pytest

from silx.gui import qt
from bliss.flint.executor import submit_to_qt_application, QtSignalQueue


def thread_target(queue):
    try:
        app = qt.QCoreApplication(['some', 'args'])
    except Exception as e:
        queue.put(e)
        raise
    queue.put(app)
    app.exec_()


@pytest.fixture(scope='session')
def qtapp():
    queue = Queue.Queue()
    th = threading.Thread(target=thread_target, args=(queue,))
    th.start()
    app = queue.get()
    assert app == qt.QApplication.instance()
    try:
        yield app
    finally:
        app.quit()  # seems to be threadsafe...
        th.join(1.)


def test_submit_to_qt_application(qtapp):
    submit = submit_to_qt_application
    assert submit(qtapp.arguments) == ['some', 'args']
    with pytest.raises(TypeError):
        submit(qtapp.arguments, 'not supported')
    assert submit(qtapp.setApplicationName, 'test') is None
    assert submit(qtapp.applicationName) == 'test'


def test_queue_from_qt_signal(qtapp):
    submit = submit_to_qt_application
    timer = submit(qt.QTimer, parent=qtapp)
    queue = QtSignalQueue(timer.timeout)
    submit(timer.start, 100)
    assert queue.get(timeout=0.150) == ()
    submit(timer.start, 100)
    gevent.sleep(0.150)
    queue.disconnect()
    assert list(queue) == [()]
    # Test idempotency
    queue.disconnect()
