# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""SpecCommand module
This module defines the classes Spec command
objects
Classes:
BaseSpecCommand
SpecCommand
SpecCommandA
"""

import sys
import types
import logging
import gevent
from gevent.event import Event
from .connection import SpecConnection
from .reply import SpecReply
from .wait import waitConnection
from .error import SpecClientTimeoutError, SpecClientError, SpecClientNotConnectedError
from bliss.common import event


class wrap_errors(object):
    def __init__(self, func):
        """Make a new function from `func', such that it catches all exceptions
        and return it as a SpecClientError object
        """
        self.func = func

    def __call__(self, *args, **kwargs):
        func = self.func
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return SpecClientError(e)

    def __str__(self):
        return str(self.func)

    def __repr__(self):
        return repr(self.func)

    def __getattr__(self, item):
        return getattr(self.func, item)


def wait_end_of_spec_cmd(cmd_obj):
    cmd_obj._reply_arrived_event.wait()

    if cmd_obj._last_reply.error:
        raise SpecClientError("command %r aborted from spec" % cmd_obj.command)
    else:
        return cmd_obj._last_reply.data


class BaseSpecCommand:
    """Base class for SpecCommand objects"""

    def __init__(self, command=None, connection=None, timeout=None):
        self.command = None
        self.connection = None
        self.specVersion = None
        if command is not None:
            self.setCommand(command)

        if connection is not None:
            if type(connection) in (str, bytes):
                #
                # connection is given in the 'host:port' form
                #
                self.connectToSpec(str(connection), timeout)
            else:
                self.connection = connection

    def connectToSpec(self, specVersion, timeout=None):
        pass

    def isConnected(self):
        return self.isSpecConnected()

    def isSpecConnected(self):
        return self.connection is not None and self.connection.isSpecConnected()

    def isSpecReady(self):
        if self.isSpecConnected():
            try:
                status_channel = self.connection.getChannel("status/ready")
                status = status_channel.read()
            except BaseException:
                pass
            else:
                return status

        return False

    def setCommand(self, command):
        self.command = command

    def __repr__(self):
        return "<SpecCommand object, command=%s>" % self.command or ""

    def __call__(self, *args, **kwargs):
        if self.command is None:
            return

        if self.connection is None:
            raise SpecClientNotConnectedError

        self.connection.connected_event.wait()

        if self.connection.serverVersion < 3:
            func = False

            if "function" in kwargs:
                func = kwargs["function"]

            # convert args list to string args list
            # it is much more convenient using .call('psvo', 12) than .call('psvo', '12')
            # a possible problem will be seen in Spec
            args = list(map(repr, args))

            if func:
                # macro function
                command = self.command + "(" + ",".join(args) + ")"
            else:
                # macro
                command = self.command + " " + " ".join(args)
        else:
            # Spec knows
            command = [self.command] + list(args)

        return self.executeCommand(
            command, kwargs.get("wait", False), kwargs.get("timeout")
        )

    def executeCommand(self, command, wait=False, timeout=None):
        pass


class SpecCommandA(BaseSpecCommand):
    """SpecCommandA is the asynchronous version of SpecCommand.
    It allows custom waiting by subclassing."""

    def __init__(self, *args, **kwargs):
        self._reply_arrived_event = Event()
        self._last_reply = None

        BaseSpecCommand.__init__(self, *args, **kwargs)

    def connectToSpec(self, specVersion, timeout=None):
        if self.connection is not None:
            event.disconnect(self.connection, "connected", self._connected)
            event.disconnect(self.connection, "disconnected", self._disconnected)

        self.connection = SpecConnection(specVersion)
        self.specVersion = specVersion

        event.connect(self.connection, "connected", self._connected)
        event.connect(self.connection, "disconnected", self._disconnected)

        if self.connection.isSpecConnected():
            self._connected()

    def connected(self):
        pass

    def _connected(self):
        self.connection.registerChannel("status/ready", self._statusChanged)

        self.connection.send_msg_hello()

        self.connected()

    def _disconnected(self):
        self.disconnected()

    def disconnected(self):
        pass

    def _statusChanged(self, ready):
        self.statusChanged(ready)

    def statusChanged(self, ready):
        pass

    def executeCommand(self, command, wait=False, timeout=None):
        self._reply_arrived_event.clear()
        self.beginWait()

        with gevent.Timeout(timeout, SpecClientTimeoutError):
            if isinstance(command, str):
                id = self.connection.send_msg_cmd_with_return(
                    command, self.replyArrived
                )
            else:
                id = self.connection.send_msg_func_with_return(
                    command, self.replyArrived
                )

            t = gevent.spawn(wrap_errors(wait_end_of_spec_cmd), self)

            if wait:
                ret = t.get()
                if isinstance(ret, SpecClientError):
                    raise ret
                elif isinstance(ret, Exception):
                    self.abort()  # abort spec
                    raise
                else:
                    return ret
            else:
                t._get = t.get

                def special_get(self, *args, **kwargs):
                    ret = self._get(*args, **kwargs)
                    if isinstance(ret, SpecClientError):
                        raise ret
                    elif isinstance(ret, Exception):
                        self.abort()  # abort spec
                        raise
                    else:
                        return ret

                setattr(t, "get", types.MethodType(special_get, t))

                return t

    def replyArrived(self, reply):
        self._last_reply = reply
        self._reply_arrived_event.set()

    def beginWait(self):
        pass

    def abort(self):
        if self.connection is None or not self.connection.isSpecConnected():
            return

        self.connection.abort()
