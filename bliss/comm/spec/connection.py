# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""SpecConnection module
Low-level module for communicating with a
remote Spec server
Classes :
SpecClientNotConnectedError -- exception class
SpecConnection
SpecConnectionDispatcher
"""
import gevent
import gevent.socket
import socket
import weakref
import logging
from bliss.common import event
from .error import SpecClientNotConnectedError
from .channel import SpecChannel
from .message import *
from .message import message as spec_message
from .reply import SpecReply
import sys

(DISCONNECTED, PORTSCANNING, WAITINGFORHELLO, CONNECTED) = (1, 2, 3, 4)
(MIN_PORT, MAX_PORT) = (6510, 6530)


def makeConnection(conn):
    """Establish a connection to Spec
    If we are in port scanning mode, try to connect using
    a port defined in the range from MIN_PORT to MAX_PORT
    """
    conn.state = DISCONNECTED
    if conn.scanport:
        conn.port = MIN_PORT

    while True:
        if conn.scanport:
            conn.state = PORTSCANNING
            if conn.port > MAX_PORT:
                raise SpecClientNotConnectedError

        try:
            s = gevent.socket.create_connection((conn.host, conn.port), timeout=0.2)
        except socket.error:
            if not conn.scanport:
                raise
        else:
            with gevent.Timeout(1, SpecClientNotConnectedError):
                conn.state = WAITINGFORHELLO
                conn.socket = s
                conn.send_msg_hello()
                m = spec_message(version=None)
                m.readFromStream(conn.socket.recv(1024))
                if m.cmd == HELLO_REPLY:
                    if conn.checkourversion(m.name):
                        conn.serverVersion = m.vers
                        return gevent.spawn(connectionHandler, conn, s)
        if conn.scanport:
            conn.port += 1


def try_connect(fu):
    def rfunc(self, *args, **kwargs):
        if self.connection_greenlet is None or self.connection_greenlet.ready():
            self.connection_greenlet = makeConnection(self)
            self.registerChannel("error", self.error)
        return fu(self, *args, **kwargs)

    return rfunc


def connectionHandler(conn, socket_to_spec):
    receivedStrings = []
    message = None
    serverVersion = None
    socket_to_spec.settimeout(None)
    conn.specConnected()

    while True:

        try:
            receivedStrings.append(socket_to_spec.recv(4096))
        except BaseException:
            receivedStrings.append(b"")

        if receivedStrings[-1] == b"":
            conn.handle_close()
            break

        s = b"".join(receivedStrings)
        consumedBytes = 0
        offset = 0

        while offset < len(s):
            if message is None:
                message = spec_message(version=serverVersion)

            consumedBytes = message.readFromStream(s[offset:])

            if consumedBytes == 0:
                break

            offset += consumedBytes

            if message.isComplete():
                try:
                    try:
                        # dispatch incoming message
                        if message.cmd == REPLY:
                            replyID = message.sn
                            if replyID > 0:
                                try:
                                    reply = conn.registeredReplies[replyID]
                                except BaseException:
                                    logging.getLogger("SpecClient").exception(
                                        "Unexpected error while receiving a message from server"
                                    )
                                else:
                                    del conn.registeredReplies[replyID]
                                    reply.update(
                                        message.data, message.type == ERROR, message.err
                                    )
                        elif message.cmd == EVENT:
                            try:
                                channel = conn.registeredChannels[message.name]
                            except KeyError:
                                pass
                            else:
                                channel.update(message.data, message.flags == DELETED)
                    except BaseException:
                        receivedStrings = [s[offset:]]
                        raise
                finally:
                    message = None

            receivedStrings = [s[offset:]]


class SpecConnection:
    """SpecConnection class
    Signals:
    connected() -- emitted when the required Spec version gets connected
    disconnected() -- emitted when the required Spec version gets disconnected
    replyFromSpec(reply id, SpecReply object) -- emitted when a reply comes from the remote Spec
    error(error code) -- emitted when an error event is received from the remote Spec
    """

    def __init__(self, specVersion):
        """Constructor
        Arguments:
        specVersion -- a 'host:port' string
        """
        self.state = DISCONNECTED
        self.connection_greenlet = None
        self.connected = False
        self.scanport = False
        self.scanname = ""
        self.registeredChannels = {}
        self.registeredReplies = {}
        self.connected_event = gevent.event.Event()
        self._completed_writing_event = gevent.event.Event()
        self.outgoing_queue = []
        self.socket_write_event = None

        tmp = str(specVersion).split(":")
        self.host = tmp[0]

        if len(tmp) > 1:
            self.port = tmp[1]
        else:
            self.port = 6789

        try:
            self.port = int(self.port)
        except BaseException:
            self.scanname = self.port
            self.port = None
            self.scanport = True

    def __str__(self):
        return "<connection to Spec, host=%s, port=%s>" % (
            self.host,
            self.port or self.scanname,
        )

    def __del__(self):
        self.disconnect()

    @try_connect
    def registerChannel(self, chanName, receiverSlot, register=True):
        """Register a channel
        Tell the remote Spec we are interested in receiving channel update events.
        If the channel is not already registered, create a new SpecChannel object,
        and connect the channel 'valueChanged' signal to the receiver slot. If the
        channel is already registered, simply add a connection to the receiver
        slot.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        receiverSlot -- any callable object in Python
        Keywords arguments:
        registrationFlag -- internal flag
        """
        chanName = str(chanName)

        try:
            if chanName not in self.registeredChannels:
                channel = SpecChannel(self, chanName, register)
                self.registeredChannels[chanName] = channel
                if channel.spec_chan_name != chanName:
                    self.registerChannel(channel.spec_chan_name, channel.update)
                channel.registered = True
            else:
                channel = self.registeredChannels[chanName]

            event.connect(channel, "valueChanged", receiverSlot)

            # channel.spec_chan_name].value
            channelValue = self.registeredChannels[channel.spec_chan_name].value
            if channelValue is not None:
                # we received a value, so emit an update signal
                channel.update(channelValue, force=True)
        except BaseException:
            logging.getLogger("SpecClient").exception(
                "Uncaught exception in SpecConnection.registerChannel"
            )

    @try_connect
    def unregisterChannel(self, chanName):
        """Unregister a channel
        Arguments:
        chanName -- a string representing the channel to unregister, i.e. 'var/toto'
        """
        chanName = str(chanName)

        if chanName in self.registeredChannels:
            self.registeredChannels[chanName].unregister()
            del self.registeredChannels[chanName]

    @try_connect
    def getChannel(self, chanName):
        """Return a channel object
        If the required channel is already registered, return it.
        Otherwise, return a new 'temporary' unregistered SpecChannel object ;
        reference should be kept in the caller or the object will get dereferenced.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        if chanName not in self.registeredChannels:
            # return a newly created temporary SpecChannel object, without
            # registering
            return SpecChannel(self, chanName, register=False)

        return self.registeredChannels[chanName]

    def error(self, error):
        """Emit the 'error' signal when the remote Spec version signals an error."""
        logging.getLogger("SpecClient").error("Error from Spec: %s", error)

        event.send(self, "error", (error,))

    def isSpecConnected(self):
        """Return True if the remote Spec version is connected."""
        return self.state == CONNECTED

    def specConnected(self):
        """Emit the 'connected' signal when the remote Spec version is connected."""
        old_state = self.state
        self.state = CONNECTED
        if old_state != CONNECTED:
            logging.getLogger("SpecClient").info(
                "Connected to %s:%s",
                self.host,
                (self.scanport and self.scanname) or self.port,
            )

            self.connected_event.set()

            event.send(self, "connected")

    def specDisconnected(self):
        """Emit the 'disconnected' signal when the remote Spec
           version is disconnected.
        """
        old_state = self.state
        self.state = DISCONNECTED
        if old_state == CONNECTED:
            logging.getLogger("SpecClient").info(
                "Disconnected from %s:%s",
                self.host,
                (self.scanport and self.scanname) or self.port,
            )

            event.send(self, "disconnected")

            self.connected_event.clear()

    def handle_close(self):
        """Handle 'close' event on socket."""
        self.connected = False
        self.serverVersion = None
        if self.socket:
            self.socket.close()
        self.registeredChannels = {}
        self.specDisconnected()

    def disconnect(self):
        """Disconnect from the remote Spec version."""
        self.handle_close()

    def checkourversion(self, name):
        """Check remote Spec version
        If we are in port scanning mode, check if the name from
        Spec corresponds to our required Spec version.
        """
        if self.scanport:
            if name == self.scanname:
                return True
            else:
                # connected version does not match
                return False
        else:
            return True

    @try_connect
    def send_msg_cmd_with_return(self, cmd, callback=None):
        """Send a command message to the remote Spec server,
           and return the reply id.
        Arguments:
        cmd -- command string, i.e. '1+1'
        """
        return self.__send_msg_with_reply(
            replyCallback=callback,
            *msg_cmd_with_return(cmd, version=self.serverVersion)
        )

    @try_connect
    def send_msg_func_with_return(self, cmd, callback=None):
        """Send a command message to the remote Spec server using the
           new 'func' feature, and return the reply id.
        Arguments:
        cmd -- command string
        """
        if self.serverVersion < 3:
            logging.getLogger("SpecClient").error(
                "Cannot execute command in Spec : feature is available since Spec server v3 only"
            )
        else:
            message = msg_func_with_return(cmd, version=self.serverVersion)
            return self.__send_msg_with_reply(replyCallback=callback, *message)

    @try_connect
    def send_msg_cmd(self, cmd):
        """Send a command message to the remote Spec server.
        Arguments:
        cmd -- command string, i.e. 'mv psvo 1.2'
        """
        self.__send_msg_no_reply(msg_cmd(cmd, version=self.serverVersion))

    @try_connect
    def send_msg_func(self, cmd):
        """Send a command message to the remote Spec server using the new 'func' feature
        Arguments:
        cmd -- command string
        """
        if self.serverVersion < 3:
            logging.getLogger("SpecClient").error(
                "Cannot execute command in Spec : feature is available since Spec server v3 only"
            )
        else:
            self.__send_msg_no_reply(msg_func(cmd, version=self.serverVersion))

    @try_connect
    def send_msg_chan_read(self, chanName, callback=None):
        """Send a channel read message, and return the reply id.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        return self.__send_msg_with_reply(
            replyCallback=callback, *msg_chan_read(chanName, version=self.serverVersion)
        )

    @try_connect
    def send_msg_chan_send(self, chanName, value, wait=False):
        """Send a channel write message.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        value -- channel value
        """
        self.__send_msg_no_reply(
            msg_chan_send(chanName, value, version=self.serverVersion), wait
        )

    @try_connect
    def send_msg_register(self, chanName):
        """Send a channel register message.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        self.__send_msg_no_reply(msg_register(chanName, version=self.serverVersion))

    @try_connect
    def send_msg_unregister(self, chanName):
        """Send a channel unregister message.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        self.__send_msg_no_reply(msg_unregister(chanName, version=self.serverVersion))

    @try_connect
    def send_msg_close(self):
        """Send a close message."""
        self.__send_msg_no_reply(msg_close(version=self.serverVersion))

    @try_connect
    def send_msg_abort(self, wait=False):
        """Send an abort message."""
        self.__send_msg_no_reply(msg_abort(version=self.serverVersion), wait)

    def send_msg_hello(self):
        """Send a hello message."""
        self.__send_msg_no_reply(msg_hello())

    def __send_msg_with_reply(self, reply, message, replyCallback=None):
        """Send a message to the remote Spec, and return the reply id.
        The reply object is added to the registeredReplies dictionary,
        with its reply id as the key. The reply id permits then to
        register for the reply using the 'registerReply' method.
        Arguments:
        reply -- SpecReply object which will receive the reply
        message -- SpecMessage object defining the message to send
        """
        replyID = reply.id
        self.registeredReplies[replyID] = reply

        if callable(replyCallback):
            reply.callback = replyCallback

        self.__send_msg_no_reply(message)

        return reply  # print "REPLY ID", replyID

    def __do_send_data(self):
        buffer = b"".join(self.outgoing_queue)
        if not buffer:
            self.socket_write_event.stop()
            self.socket_write_event = None
            self._completed_writing_event.set()
            return
        sent_bytes = self.socket.send(buffer)
        self.outgoing_queue = [buffer[sent_bytes:]]

    def __send_msg_no_reply(self, message, wait=False):
        """Send a message to the remote Spec.
        If a reply is sent depends only on the message, and not on the
        method to send the message. Using this method, any reply is
        lost.
        """
        self.outgoing_queue.append(message.sendingString())
        if self.socket_write_event is None:
            if wait:
                self._completed_writing_event.clear()
            self.socket_write_event = gevent.get_hub().loop.io(self.socket.fileno(), 2)
            self.socket_write_event.start(self.__do_send_data)
            if wait:
                self._completed_writing_event.wait()
