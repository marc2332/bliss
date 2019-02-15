import sys

from gevent import greenlet
from gevent import hub
import gevent

MASKED_GREENLETS = dict()


class KillMask:
    def __init__(self, masked_kill_nb=-1):
        """
        masked_kill_nb: nb of masked kill
                 < 0 mean all kills are masked.
                 if > 0, at each kill attempt the counter decrements until 0, then the greenlet can be killed
        """
        self.__greenlet = gevent.getcurrent()
        self.__kill_counter = masked_kill_nb

    def __enter__(self):
        self.__exception = None
        MASKED_GREENLETS.setdefault(self.__greenlet, set()).add(self)

    def __exit__(self, exc_type, value, traceback):
        MASKED_GREENLETS[self.__greenlet].remove(self)
        if MASKED_GREENLETS[self.__greenlet]:
            return
        MASKED_GREENLETS.pop(self.__greenlet)
        if self.__exception is not None:
            raise self.__exception

    def set_throw(self, exception):
        if self.__kill_counter:
            self.__exception = exception
        else:  # reach 0
            self.__exception = None
        cnt = self.__kill_counter
        self.__kill_counter -= 1
        return not cnt


def protect_from_kill(fu):
    def func(*args, **kwargs):
        with KillMask():
            return fu(*args, **kwargs)

    return func


def protect_from_one_kill(fu):
    def func(*args, **kwargs):
        with KillMask(masked_kill_nb=1):
            return fu(*args, **kwargs)

    return func


# gevent.greenlet module patch
class Greenlet(greenlet.Greenlet):
    def throw(self, exception):
        if isinstance(exception, gevent.timeout.Timeout):
            return super().throw(exception)

        masks = MASKED_GREENLETS.get(self)
        if masks:
            for m in list(masks):
                if m.set_throw(exception):
                    super().throw(exception)
        else:
            super().throw(exception)


gevent.spawn = Greenlet.spawn
gevent.spawn_later = Greenlet.spawn_later
