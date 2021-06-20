from functools import wraps
from contextlib import contextmanager
import logging

import asyncio
import aiogevent
from gevent import monkey
from gevent import greenlet, timeout
import gevent


logger = logging.getLogger(__name__)


class KillMask:
    """All exceptions which are the result of a `kill(SomeException)`
    call on the greenlet in which the KillMask context is entered,
    will be delayed until context exit, except for `gevent.Timeout`.

    Upon exit, only the last captured exception is re-raised.

    Optionally we can set a limit to the number of `kill` calls
    that will be delayed.

    Warning: this does not delay interrupts.
    """

    def __init__(self, masked_kill_nb=-1):
        """
        masked_kill_nb: number of masked `kill` calls that will be delayed
                  > 0 this ammount of kills will be delayed
                 == 0 no kill is delayed
                  < 0 unlimited
        """
        self.__masked_kill_nb = masked_kill_nb
        self.__allowed_capture_nb = masked_kill_nb
        self.__last_captured_exception = None

    @property
    def _bliss_greenlet(self):
        glt = gevent.getcurrent()
        if isinstance(glt, BlissGreenlet):
            return glt
        elif glt.parent is not None:
            logger.warning("KillMask will not work in the current greenlet: %s", glt)
        return None

    def __enter__(self):
        glt = self._bliss_greenlet
        if glt is None:
            return
        self.__allowed_capture_nb = self.__masked_kill_nb
        self.__last_captured_exception = None
        glt.kill_masks.add(self)

    def __exit__(self, exc_type, value, traceback):
        glt = self._bliss_greenlet
        if glt is None:
            return
        glt.kill_masks.remove(self)
        if not glt.kill_masks and self.__last_captured_exception is not None:
            raise self.__last_captured_exception

    @property
    def last_captured_exception(self):
        return self.__last_captured_exception

    def capture_exception(self, exception):
        capture = bool(self.__allowed_capture_nb)
        if capture:
            self.__last_captured_exception = exception
            self.__allowed_capture_nb -= 1
        else:
            self.__last_captured_exception = None
        return capture


@contextmanager
def AllowKill():
    """
    This will unmask the kill protection for the current greenlet.
    """
    glt = gevent.getcurrent()
    if isinstance(glt, BlissGreenlet):
        with glt.disable_kill_masks() as kill_masks:
            for kill_mask in kill_masks:
                if kill_mask.last_captured_exception:
                    raise kill_mask.last_captured_exception
            yield
    else:
        yield


def protect_from_kill(method):
    @wraps(method)
    def wrapper(*args, **kwargs):
        with KillMask():
            return method(*args, **kwargs)

    return wrapper


def protect_from_one_kill(method):
    @wraps(method)
    def wrapper(*args, **kwargs):
        with KillMask(masked_kill_nb=1):
            return method(*args, **kwargs)

    return wrapper


_GeventTimeout = gevent.timeout.Timeout
_GeventGreenlet = greenlet.Greenlet


class BlissGreenlet(_GeventGreenlet):
    """KillMask can only work when entered in a greenlet of type `BlissGreenlet`
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.__kill_masks = set()

    @property
    def kill_masks(self):
        return self.__kill_masks

    @contextmanager
    def disable_kill_masks(self):
        kill_masks = self.__kill_masks
        self.__kill_masks = set()
        try:
            yield kill_masks
        finally:
            self.__kill_masks = kill_masks

    def throw(self, exception):
        # This is executed in the Hub which is the reason
        # we cannot use gevent.local.local to store the
        # kill masks for each greenlet.
        if isinstance(exception, _GeventTimeout):
            return super().throw(exception)

        if self.__kill_masks:
            captured_in_all_masks = True
            for kill_mask in self.__kill_masks:
                captured_in_all_masks &= kill_mask.capture_exception(exception)
            if captured_in_all_masks:
                return

        super().throw(exception)

    def get(self, *args, **keys):
        try:
            return super().get(*args, **keys)
        except BlissTimeout:
            raise
        except _GeventTimeout as tmout:
            raise BlissTimeout(exception=tmout.exception)


class BlissTimeout(_GeventTimeout):
    """KillMask can only work when timeouts are of type `BlissTimeout`
    """

    def _on_expiration(self, prev_greenlet, ex):
        if isinstance(prev_greenlet, BlissGreenlet):
            # Make sure the exception is not captured by
            # a KillMask
            super(BlissGreenlet, prev_greenlet).throw(ex)
        else:
            prev_greenlet.throw(ex)


def patch_gevent():
    asyncio.set_event_loop_policy(aiogevent.EventLoopPolicy())

    monkey.patch_all(thread=False)

    # For KillMask
    gevent.spawn = BlissGreenlet.spawn
    gevent.spawn_later = BlissGreenlet.spawn_later
    timeout.Timeout = BlissTimeout
    gevent.Timeout = BlissTimeout


# For backward compatibility
Greenlet = BlissGreenlet
Timeout = BlissTimeout
