# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helper about string formatting"""

from __future__ import annotations
from typing import MutableMapping
from typing import Callable
from typing import List
from typing import Tuple

import weakref
from silx.gui import qt


class InvalidatableSignal(qt.QObject):
    """"Manage a signal which can be invalidated instead of been triggered all
    the time.
    """

    triggered = qt.Signal()

    def __init__(self, parent: qt.QObject = None):
        super(InvalidatableSignal, self).__init__(parent=parent)
        self.__invalidated = False

    def trigger(self):
        """Trigger the signal"""
        self.__invalidated = False
        self.triggered.emit()

    def triggerIf(self, condition=None):
        """Trigger the signal only if this `condition` is True.

        Else this object is invalidated.
        """
        if condition:
            self.trigger()
        else:
            self.__invalidated = True

    def invalidate(self):
        """Invalidate this object.

        Calling `validate` will execute the trigger.
        """
        self.__invalidated = True

    def validate(self):
        """Trigger the signal, only if this object was invalidated."""
        if self.__invalidated:
            self.trigger()


class EventAggregator:
    """Allow to stack events and to trig them time to time"""

    def __init__(self):
        self.__eventStack = []
        self.__callbacks: MutableMapping[
            Callable, Callable
        ] = weakref.WeakKeyDictionary()

    def empty(self):
        """Returns true if there is no stored events."""
        return len(self.__eventStack) == 0

    def callbackTo(self, callback):
        """Create a callback for events which have to be emitted to this
        `callback`

        Returns a callable which have to be used to receive the event
        """
        internalCallback = self.__callbacks.get(callback, None)
        if internalCallback is None:

            def func(*args, **kwargs):
                self.__eventStack.append((callback, args, kwargs))

            internalCallback = func
            self.__callbacks[callback] = internalCallback

        return internalCallback

    def flush(self):
        """Flush all the stored event to the targetted callbacks.
        """
        eventStack, self.__eventStack = self.reduce(self.__eventStack)
        for callback, args, kwargs in eventStack:
            callback(*args, **kwargs)

    def reduce(self, eventStack: List) -> Tuple[List, List]:
        """This method can be implemented to reduce the amount of event in the
        stack before emitting them.

        Returns the events to process now, and the events to process next time.
        """
        return eventStack, []
