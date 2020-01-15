import sys
import gevent
import pytest

from bliss.common.greenlet_utils import protect_from_kill, protect_from_one_kill
from bliss.common.greenlet_utils import AllowKill


def test_protect_from_kill():
    event1 = gevent.event.Event()
    event2 = gevent.event.Event()
    event3 = gevent.event.Event()

    @protect_from_kill
    def target():
        event1.set()
        event2.wait()
        event3.set()

    task = gevent.spawn(target)
    event1.wait()
    task.kill(block=False)
    event2.set()
    task.join()
    assert event3.is_set()


def test_protect_from_one_kill():
    event1 = gevent.event.Event()
    event2 = gevent.event.Event()
    event3 = gevent.event.Event()
    event4 = gevent.event.Event()
    event5 = gevent.event.Event()

    @protect_from_one_kill
    def target():
        event1.set()
        event2.wait()
        event3.set()
        event4.wait()
        event5.set()

    task = gevent.spawn(target)
    event1.wait()
    task.kill(block=False)
    event2.set()
    gevent.sleep(0)
    assert event3.is_set()
    task.kill(block=False)
    event4.set()
    task.join()
    assert not event5.is_set()


def test_protect_from_kill_all():
    event1 = gevent.event.Event()
    event2 = gevent.event.Event()
    event3 = gevent.event.Event()

    @protect_from_kill
    def target():
        event1.set()
        event2.wait()
        event3.set()

    task = gevent.spawn(target)
    event1.wait()
    gevent.killall([task], block=False)
    event2.set()
    task.join()
    assert event3.is_set()


def test_unkillmask_with_kill_before_mask():
    event1 = gevent.event.Event()
    event2 = gevent.event.Event()
    event3 = gevent.event.Event()

    @protect_from_kill
    def target2():
        event2.wait()
        with AllowKill():
            event3.set()

    @protect_from_kill
    def target():
        event1.set()
        target2()

    task = gevent.spawn(target)
    event1.wait()
    task.kill(block=False)
    event2.set()
    task.kill(block=False)
    task.join()
    assert not event3.is_set()


def test_unkillmask_with_kill_after_mask():
    event1 = gevent.event.Event()
    event2 = gevent.event.Event()
    event3 = gevent.event.Event()

    @protect_from_kill
    def target2():
        event1.set()
        with AllowKill():
            event2.wait()
            event3.set()

    @protect_from_kill
    def target():
        target2()

    task = gevent.spawn(target)
    event1.wait()
    task.kill(block=False)
    event2.set()
    task.join()
    assert not event3.is_set()


def test_timeout_with_kill_mask():
    @protect_from_kill
    def f():
        with gevent.Timeout(0.1, RuntimeError("Bla")):
            gevent.sleep(1)

    t = gevent.spawn(f)
    with pytest.raises(RuntimeError):
        with gevent.Timeout(0.2):
            t.get()
    t.kill()


def test_exception_with_kill_mask():
    event = gevent.event.Event()

    @protect_from_kill
    def f():
        with AllowKill():
            event.set()
            gevent.sleep(1)

    t = gevent.spawn(f)
    with gevent.Timeout(1):
        event.wait()
    with pytest.raises(AttributeError):
        t.kill(block=False, exception=AttributeError)
        t.get()
