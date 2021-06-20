from contextlib import contextmanager
from functools import wraps

import asyncio
import aiogevent
from gevent import monkey
from gevent import greenlet, timeout
import gevent

GREENLET_MASK_STATE = dict()


class KillMask:
    """All exceptions which are the result of a `kill(SomeException)`
    call on the greenlet in which the KillMask context is entered,
    will be delayed until context exit, except for `gevent.Timeout`.

    Upon exit, only the last capture exception is re-raised.

    Optionally we can set a limit to the number of `kill` calls
    will be delayed.

    Warning: this does not delay interrupts.
    """

    def __init__(self, masked_kill_nb=-1):
        """
        masked_kill_nb: number of masked `kill` calls that will be delayed
                  > 0 this ammount of kills will be delayed
                 == 0 no kill is delayed
                  < 0 unlimited
        """
        self.__greenlet = gevent.getcurrent()
        self.__masked_kill_nb = masked_kill_nb
        self.__allowed_kills = masked_kill_nb
        self.__last_captured_exception = None

    def __enter__(self):
        self.__allowed_kills = self.__masked_kill_nb
        self.__last_captured_exception = None
        GREENLET_MASK_STATE.setdefault(self.__greenlet, set()).add(self)

    def __exit__(self, exc_type, value, traceback):
        GREENLET_MASK_STATE[self.__greenlet].remove(self)
        if GREENLET_MASK_STATE[self.__greenlet]:
            return
        GREENLET_MASK_STATE.pop(self.__greenlet)
        if self.__last_captured_exception is not None:
            raise self.__last_captured_exception

    @property
    def last_captured_exception(self):
        return self.__last_captured_exception

    def capture_exception(self, exception):
        capture = bool(self.__allowed_kills)
        if capture:
            self.__last_captured_exception = exception
        else:
            self.__last_captured_exception = None
        self.__allowed_kills -= 1
        return capture


@contextmanager
def AllowKill():
    """
    This will unmask the kill protection for the current greenlet.
    """
    current_greenlet = gevent.getcurrent()
    kill_masks = GREENLET_MASK_STATE.pop(current_greenlet, set())
    try:
        for kill_mask in kill_masks:
            if kill_mask.last_captured_exception:
                raise kill_mask.last_captured_exception
        yield
    finally:
        if kill_masks:
            GREENLET_MASK_STATE[current_greenlet] = kill_masks


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

    def throw(self, exception):
        if isinstance(exception, _GeventTimeout):
            return super().throw(exception)

        kill_masks = GREENLET_MASK_STATE.get(self)
        if kill_masks:
            captured_in_all_masks = True
            for kill_mask in list(kill_masks):
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
    """KillMask can only work when timeouts are of type `BlissGreenlet`
    """

    def _on_expiration(self, prev_greenlet, ex):
        if isinstance(prev_greenlet, BlissGreenlet):
            # Make sure the exception is not captured
            super(BlissGreenlet, prev_greenlet).throw(ex)
        else:
            prev_greenlet.throw(ex)


def patch_gevent():
    asyncio.set_event_loop_policy(aiogevent.EventLoopPolicy())

    monkey.patch_all(thread=False)

    gevent.spawn = BlissGreenlet.spawn
    gevent.spawn_later = BlissGreenlet.spawn_later
    timeout.Timeout = BlissTimeout
    gevent.Timeout = BlissTimeout


# For backward compatitibilty
Greenlet = BlissGreenlet
Timeout = BlissTimeout
