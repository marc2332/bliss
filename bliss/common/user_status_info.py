# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
This module is a central point for function to provide human readable
information to the user.
"""

import weakref
import contextlib
import functools

_USER_MESSAGE_STATUS = weakref.WeakKeyDictionary()
_DISPLAY_CALLBACK = functools.partial(print, sep=",", end="\r")


@contextlib.contextmanager
def status_message():
    """
    Helper to inform end user about a status message
    """

    class K:
        pass

    key = K()

    def set(message):
        set_user_status_message(key, message)

    try:
        yield set
    finally:
        remove_user_status_message(key)


def set_user_status_message(key, message):
    """
    Set a message to the end user about a status of something.
    example: when a scan is in pause during a refill.
    """
    _USER_MESSAGE_STATUS[key] = message
    trigger_callback()


def remove_user_status_message(key):
    if _USER_MESSAGE_STATUS.pop(key, None) is not None:
        trigger_callback()


def trigger_callback():
    if _DISPLAY_CALLBACK is not None:
        _DISPLAY_CALLBACK(*_USER_MESSAGE_STATUS.values())


def set_display_callback(func):
    """
    Change the global display of status information
    Default display callback is print with sep=',' and end='\r'.
    Can be set to None to disable display of status messages
    func -- musst have a signature like func(*messages)
    """
    global _DISPLAY_CALLBACK
    _DISPLAY_CALLBACK = func


@contextlib.contextmanager
def callback():
    prev_display = _DISPLAY_CALLBACK
    try:
        yield set_display_callback
    finally:
        set_display_callback(prev_display)
