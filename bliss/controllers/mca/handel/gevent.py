"""Provide gevent compatibility.

Usage:
>>> from handel.gevent import patch
>>> patch()
"""

from __future__ import absolute_import

from functools import wraps
from gevent import threadpool

from .interface import handel


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
    for name in dir(handel):
        if name.startswith("xia"):
            func = getattr(handel, name)
            setattr(handel, name, green(func))
