
import gevent

from bliss.common.greenlet_utils import protect_from_kill


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
