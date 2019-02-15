
import sys
import gevent

from bliss.common.greenlet_utils import protect_from_kill, protect_from_one_kill


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
