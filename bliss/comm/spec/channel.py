# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""SpecChannel module
This module defines the SpecChannel class
"""

from .wait import waitReply
from .error import SpecClientTimeoutError
from bliss.common import event
import gevent
import weakref
import types
import logging

(DOREG, DONTREG, WAITREG) = (0, 1, 2)


class SpecChannel:
    """SpecChannel class
    Represent a channel in Spec
    Signals:
    valueChanged(channelValue, channelName) -- emitted when the channel gets updated
    """

    def __init__(self, connection, channelName, register=True):
        """Constructor
        Arguments:
        connection -- a SpecConnection object
        channelName -- string representing a channel name, i.e. 'var/toto'
        """
        self.connection = weakref.ref(connection)
        self.name = channelName

        if channelName.startswith("var/") and "/" in channelName[4:]:
            l = channelName.split("/")
            self.spec_chan_name = "/".join((l[0], l[1]))

            if len(l) == 3:
                self.access1 = l[2]
                self.access2 = None
            else:
                self.access1 = l[2]
                self.access2 = l[3]
        else:
            self.spec_chan_name = self.name
            self.access1 = None
            self.access2 = None
        self.registrationFlag = DOREG if register else DONTREG
        self.isdisconnected = True
        self.registered = False
        self.value = None

        event.connect(connection, "connected", self.connected)
        event.connect(connection, "disconnected", self.disconnected)

        if connection.isSpecConnected():
            self.connected()

    def connected(self):
        """Do registration when Spec gets connected
        If registration flag is WAITREG put the flag to DOREG if not yet connected,
        and register if DOREG
        """
        if self.registrationFlag == WAITREG:
            if self.isdisconnected:
                self.registrationFlag = DOREG

        self.isdisconnected = False

        if self.registrationFlag == DOREG:
            if not self.registered:
                self.register()

    def disconnected(self):
        """Reset channel object when Spec gets disconnected."""
        self.value = None
        self.isdisconnected = True
        self.registered = False

    def unregister(self):
        """Unregister channel."""
        connection = self.connection()

        if connection is not None:
            connection.send_msg_unregister(self.spec_chan_name)
            self.registered = False
            self.value = None

    def register(self):
        """Register channel
        Registering a channel means telling the server we want to receive
        update events when a channel value changes on the server side.
        """
        if self.spec_chan_name != self.name:
            return

        connection = self.connection()

        if connection is not None:
            connection.send_msg_register(self.spec_chan_name)
            self.registered = True

    def _coerce(self, value):
        try:
            value = int(value)
        except BaseException:
            try:
                value = float(value)
            except BaseException:
                pass
        return value

    def update(self, channelValue, deleted=False, force=False):
        """Update channel's value and emit the 'valueChanged' signal."""
        if isinstance(channelValue, dict) and self.access1 is not None:
            if self.access1 in channelValue:
                if deleted:
                    event.send(self, "valueChanged", (None, self.name))
                else:
                    if self.access2 is None:
                        if (
                            force
                            or self.value is None
                            or self.value != channelValue[self.access1]
                        ):
                            if isinstance(channelValue[self.access1], dict):
                                self.value = channelValue[self.access1].copy()
                            else:
                                self.value = self._coerce(channelValue[self.access1])
                            event.send(self, "valueChanged", (self.value, self.name))
                    else:
                        if self.access2 in channelValue[self.access1]:
                            if deleted:
                                event.send(self, "valueChanged", (None, self.name))
                            else:
                                if (
                                    force
                                    or self.value is None
                                    or self.value
                                    != channelValue[self.access1][self.access2]
                                ):
                                    self.value = self._coerce(
                                        channelValue[self.access1][self.access2]
                                    )
                                    event.send(
                                        self, "valueChanged", (self.value, self.name)
                                    )
            return

        if isinstance(self.value, dict) and isinstance(channelValue, dict):
            # update dictionary
            if deleted:
                for key, val in channelValue.items():
                    if isinstance(val, dict):
                        for k in val:
                            try:
                                del self.value[key][k]
                            except KeyError:
                                pass
                        if len(self.value[key]) == 1 and None in self.value[key]:
                            self.value[key] = self.value[key][None]
                    else:
                        try:
                            del self.value[key]
                        except KeyError:
                            pass
            else:
                for k1, v1 in channelValue.items():
                    if isinstance(v1, dict):
                        try:
                            self.value[k1].update(v1)
                        except KeyError:
                            self.value[k1] = v1
                        except AttributeError:
                            self.value[k1] = {None: self.value[k1]}
                            self.value[k1].update(v1)
                    else:
                        if k1 in self.value and isinstance(self.value[k1], dict):
                            self.value[k1][None] = v1
                        else:
                            self.value[k1] = v1
            value2emit = self.value.copy()
        else:
            if deleted:
                self.value = None
            else:
                self.value = channelValue
            value2emit = self.value

        event.send(self, "valueChanged", (value2emit, self.name))

    def read(self, timeout=3, force_read=False):
        """Read the channel value
        If channel is registered, just return the internal value,
        else obtain the channel value and return it.
        """
        if not force_read and self.registered:
            if self.value is not None:
                # we check 'value is not None' because the
                # 'registered' flag could be set, but before
                # the message with the channel value arrived
                return self.value

        connection = self.connection()

        if connection is not None:
            # make sure spec is connected, we give a short timeout
            # because it is supposed to be the case already
            value = waitReply(
                connection,
                "send_msg_chan_read",
                (self.spec_chan_name,),
                timeout=timeout,
            )
            if value is None:
                raise RuntimeError("could not read channel %r" % self.spec_chan_name)
            self.update(value)
            return self.value

    def write(self, value, wait=False):
        """Write a channel value."""
        connection = self.connection()

        if connection is not None:
            if self.access1 is not None:
                if self.access2 is None:
                    value = {self.access1: value}
                else:
                    value = {self.access1: {self.access2: value}}

            connection.send_msg_chan_send(self.spec_chan_name, value, wait)
