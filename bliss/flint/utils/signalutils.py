# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helper about string formatting"""


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
