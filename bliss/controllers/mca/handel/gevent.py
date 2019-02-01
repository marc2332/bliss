"""Provide gevent compatibility.

Usage:
>>> from handel.gevent import patch
>>> patch()
"""

from __future__ import absolute_import

from functools import wraps
from gevent import threadpool

from . import interface


# Green pool

# The 'maxsize=1' argument provides implicit locking
POOL = threadpool.ThreadPool(maxsize=1)


# Green decorator


def green(func, pool=POOL):
    """Make a given function gevent-compatible by running
    it in a gevent threadpool."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        return pool.apply(func, args, kwargs)

    return wrapper


# Patch function


def patch():
    """Provide gevent compatibility.

    Usage:
    >>> from handel.gevent import patch
    >>> patch()
    """
    # Gevent-compatible version of handel FFI library
    gevent_handel = type("GeventFFILibrary", (), {})()
    # Populate gevent_handel
    for name in dir(interface.handel):
        if name.startswith("xia"):
            func = getattr(interface.handel, name)
            setattr(gevent_handel, name, green(func))
    # Patch
    interface.handel = gevent_handel
