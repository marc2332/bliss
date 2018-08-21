import sys

from gevent import greenlet
from gevent import hub
import gevent

MASKED_GREENLETS = dict()


class KillMask:
    def __init__(self):
        self.__greenlet = gevent.getcurrent()

    def __enter__(self):
        self.__func, self.__exception, self.__waiter = None, None, None
        MASKED_GREENLETS.setdefault(self.__greenlet, set()).add(self)

    def __exit__(self, exc_type, value, traceback):
        MASKED_GREENLETS[self.__greenlet].remove(self)
        if MASKED_GREENLETS[self.__greenlet]:
            return
        MASKED_GREENLETS.pop(self.__greenlet)
        if self.__func:
            self.__greenlet.parent.loop.run_callback(
                self.__func, self.__greenlet, self.__exception, self.__waiter
            )
            gevent.sleep(0)
        elif self.__exception is not None:
            gevent.get_hub().loop.run_callback(self.__greenlet.throw, self.__exception)

    def set_kill(self, func, exception, waiter):
        self.__func = func
        self.__exception = exception
        self.__waiter = waiter

    def set_hub_kill(self, exception):
        self.__exception = exception


def protect_from_kill(fu):
    def func(*args, **kwargs):
        with KillMask():
            return fu(*args, **kwargs)

    return func


# gevent.greenlet module patch

saved_kill = greenlet._kill


def _patched_kill(greenlet, exception, waiter):
    masks = MASKED_GREENLETS.get(greenlet)
    if masks:
        for m in masks:
            m.set_kill(saved_kill, exception, waiter)
    else:
        saved_kill(greenlet, exception, waiter)


# Alter the true scope of the greenlet module.
# With gevent >= 1.3, the module would be typically be 'gevent._greenlet',
# with its globals copied to 'gevent.greenlet'. That means patching
# 'greenlet._kill' doesn't work since the methods of the 'Greenlet' class
# are looking for '_kill' in the 'gevent._greenlet' namespace.
sys.modules[greenlet.__name__]._kill = _patched_kill


# gevent.hub module patch


def _hub_patched_kill(greenlet, exception):
    masks = MASKED_GREENLETS.get(greenlet)
    if masks:
        for m in masks:
            m.set_hub_kill(exception)
    elif not greenlet.dead:
        gevent.get_hub().loop.run_callback(greenlet.throw, exception)


hub.kill = _hub_patched_kill
