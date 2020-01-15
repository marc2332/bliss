import sys
import weakref
import threading
from contextlib import contextmanager
from functools import wraps

from gevent import greenlet, timeout, getcurrent
from gevent.timeout import string_types
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

    @property
    def exception(self):
        return self.__exception

    def set_throw(self, exception):
        if self.__kill_counter:
            self.__exception = exception
        else:  # reach 0
            self.__exception = None
        cnt = self.__kill_counter
        self.__kill_counter -= 1
        return not cnt


@contextmanager
def AllowKill():
    """
    This will unmask the kill protection for the current greenlet.
    """
    current_greenlet = gevent.getcurrent()
    previous_set_mask = MASKED_GREENLETS.pop(current_greenlet, set())
    try:
        for killmask in previous_set_mask:
            if killmask.exception:
                raise killmask.exception
        yield
    finally:
        if previous_set_mask:
            MASKED_GREENLETS[current_greenlet] = previous_set_mask


def protect_from_kill(fu):
    @wraps(fu)
    def func(*args, **kwargs):
        with KillMask():
            return fu(*args, **kwargs)

    return func


def protect_from_one_kill(fu):
    @wraps(fu)
    def func(*args, **kwargs):
        with KillMask(masked_kill_nb=1):
            return fu(*args, **kwargs)

    return func


# gevent.greenlet module patch
_ori_timeout = gevent.timeout.Timeout


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

    def get(self, *args, **keys):
        try:
            return super().get(*args, **keys)
        except _ori_timeout as tmout:
            t = Timeout(exception=tmout.exception)
            raise t


gevent.spawn = Greenlet.spawn
gevent.spawn_later = Greenlet.spawn_later

# timeout patch
class Timeout(gevent.timeout.Timeout):
    def start(self):
        """Schedule the timeout."""
        if self.pending:
            raise AssertionError(
                "%r is already started; to restart it, cancel it first" % self
            )

        if self.seconds is None:
            # "fake" timeout (never expires)
            return

        if (
            self.exception is None
            or self.exception is False
            or isinstance(self.exception, string_types)
        ):
            # timeout that raises self
            throws = self
        else:
            # regular timeout with user-provided exception
            throws = self.exception

        # Make sure the timer updates the current time so that we don't
        # expire prematurely.

        # start the patch
        current = getcurrent()
        if isinstance(current, Greenlet):  # bliss greenlet
            self.timer.start(super(Greenlet, getcurrent()).throw, throws, update=True)
        else:  # default
            self.timer.start(getcurrent().throw, throws, update=True)


timeout.Timeout = Timeout
gevent.Timeout = Timeout

# patch hub to destroy it when the thread is finished


class Hub(hub.Hub):
    _lock = threading.Lock()

    def _sync(fn):
        @wraps(fn)
        def f(*args, **kwargs):
            with Hub._lock:
                return fn(*args, *kwargs)

        return f

    @_sync
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = threading.current_thread()
        if current is not threading.main_thread():
            weakref.finalize(current, self.destroy)

    @_sync
    def destroy(self):
        return super().destroy()


hub.set_default_hub_class(Hub)
