# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Emulator :mod:`~bliss.controllers.emulator.Server` and \
:mod:`~bliss.controllers.emulator.BaseDevice`

Quick start
-----------

To create a server use the following configuration as a starting point:

.. code-block:: yaml

    name: my_emulator
    devices:
        - class: SCPI
          transports:
              - type: tcp
                url: :25000

To start the server you can do something like::

    $ python -m bliss.controllers.emulator my_emulator

(bliss also provides a ``bliss-emulator`` script which basically does the same)

An emulator how-to is available :ref:`here <bliss-emulator-how-to>`.
"""

from __future__ import print_function

import os
import pty
import sys
import logging
import weakref

import gevent
from gevent.baseserver import BaseServer
from gevent.server import StreamServer
from gevent.fileobject import FileObject

_log = logging.getLogger('emulator')

__all__ = ['Server', 'BaseDevice', 'EmulatorServerMixin',
           'SerialServer', 'TCPServer', 'main', 'create_server_from_config']


class EmulatorServerMixin(object):
    """
    Mixin class for TCP/Serial servers to handle line based commands.
    Internal usage only
    """

    def __init__(self, device=None, newline=None, baudrate=None):
        self.device = device
        self.baudrate = baudrate
        self.newline = device.newline if newline is None else newline
        self.special_messages = set(device.special_messages)
        self.connections = {}
        name = '{0}({1}, device={2})'.format(type(self).__name__, self.address,
                                             device.name)
        self._log = logging.getLogger('{0}.{1}'.format(_log.name, name))
        self._log.info('listening on %s (newline=%r)', self.address,
                       self.newline)

    def handle(self, sock, addr):
        file_obj = sock.makefile(mode='rb')
        self.connections[addr] = file_obj, sock
        try:
            return self.__handle(sock, file_obj)
        finally:
            file_obj.close()
            del self.connections[addr]

    def __handle(self, sock, file_obj):
        """
        Handle new connection and requests

        Arguments:
            sock (gevent.socket.socket): new socket resulting from an accept
            addr tuple): address (tuple of host, port)
        """
        if self.newline == '\n' and not self.special_messages:
            for line in file_obj:
                self.handle_line(sock, line)
        else:
            # warning: in this mode read will block even if client
            # disconnects. Need to find a better way to handle this
            buff = ''
            finish = False
            while not finish:
                readout = file_obj.read(1)
                if not readout:
                    return
                buff += readout
                if buff in self.special_messages:
                    lines = buff,
                    buff = ''
                else:
                    lines = buff.split(self.newline)
                    buff, lines = lines[-1], lines[:-1]
                for line in lines:
                    if not line:
                        return
                    self.handle_line(sock, line)

    def handle_line(self, sock, line):
        """
        Handle a single command line. Emulates a delay if baudrate is defined
        in the configuration.

        Arguments:
            sock (gevent.socket.socket): new socket resulting from an accept
            addr (tuple): address (tuple of host, port)
            line (str): line to be processed

        Returns:
            str: response to give to client or None if no response
        """
        self.pause(len(line))
        response = self.device.handle_line(line)
        if response is not None:
            self.pause(len(response))
            sock.sendall(response)
        return response

    def pause(self, nb_bytes):
        """
        Emulate a delay simulating the transport of the given number of bytes,
        correspoding to the baudrate defined in the configuration

        Arguments:
            nb_bytes (int): number of bytes to transport
        """
        # emulate baudrate
        if not self.baudrate:
            return
        byterate = self.baudrate / 10.0
        sleep = nb_bytes / byterate
        gevent.sleep(sleep)

    def broadcast(self, msg):
        for _, (_, sock) in self.connections.items():
            try:
                sock.sendall(msg)
            except:
                self._log.exception('error in broadcast')


class SerialServer(BaseServer, EmulatorServerMixin):
    """
    Serial line emulation server. It uses :func:`pty.opentpy` to open a
    pseudo-terminal simulating a serial line.

    .. note::
        Since :func:`pty.opentpy` opens a non configurable file descriptor, it
        is impossible to predict which /dev/pts/<N> will be used.
        You have to be attentive to the first logging info messages when the
        server is started. They indicate which device is in use  :-(
    """

    def __init__(self, *args, **kwargs):
        device = kwargs.pop('device')
        e_kwargs = dict(baudrate=kwargs.pop('baudrate', None),
                        newline=kwargs.pop('newline', None))
        BaseServer.__init__(self, None, *args, **kwargs)
        EmulatorServerMixin.__init__(self, device, **e_kwargs)

    def set_listener(self, listener):
        """
        Override of :meth:`~gevent.baseserver.BaseServer.set_listener` to
        initialize a pty and properly fill the address
        """
        if listener is None:
            self.master, self.slave = pty.openpty()
        else:
            self.master, self.slave = listener
        self.address = os.ttyname(self.slave)
        self.fileobj = FileObject(self.master, mode='rb')

    @property
    def socket(self):
        """
        Override of :meth:`~gevent.baseserver.BaseServer.socket` to return a
        socket object for the pseudo-terminal file object
        """
        return self.fileobj._sock

    def _do_read(self):
        # override _do_read to properly handle pty
        try:
            self.do_handle(self.socket, self.address)
        except:
            self.loop.handle_error(([self.address], self), *sys.exc_info())
            if self.delay >= 0:
                self.stop_accepting()
                self._timer = self.loop.timer(self.delay)
                self._timer.start(self._start_accepting_if_started)
                self.delay = min(self.max_delay, self.delay * 2)


class TCPServer(StreamServer, EmulatorServerMixin):
    """
    TCP emulation server
    """

    def __init__(self, *args, **kwargs):
        listener = kwargs.pop('url')
        if isinstance(listener, list):
            listener = tuple(listener)
        device = kwargs.pop('device')
        e_kwargs = dict(baudrate=kwargs.pop('baudrate', None),
                        newline=kwargs.pop('newline', None))
        StreamServer.__init__(self, listener, *args, **kwargs)
        EmulatorServerMixin.__init__(self, device, **e_kwargs)

    def handle(self, sock, addr):
        info = self._log.info
        info('new connection from %s', addr)
        EmulatorServerMixin.handle(self, sock, addr)
        info('client disconnected %s', addr)


class BaseDevice(object):
    """
    Base intrument class. Override to implement an emulator for a specific
    device
    """

    DEFAULT_NEWLINE='\n'

    special_messages = set()

    def __init__(self, name, newline=None, **kwargs):
        self.name = name
        self.newline = self.DEFAULT_NEWLINE if newline is None else newline
        self._log = logging.getLogger('{0}.{1}'.format(_log.name, name))
        self.__transports = weakref.WeakKeyDictionary()
        if kwargs:
            self._log.warning('constructor keyword args ignored: %s',
                              ', '.join(kwargs.keys()))

    @property
    def transports(self):
        """the list of registered transports"""
        return self.__transports.keys()

    @transports.setter
    def transports(self, transports):
        self.__transports.clear()
        for transport in transports:
            self.__transports[transport] = None

    def handle_line(self, line):
        """
        To be implemented by the device.

        Raises: NotImplementedError
        """
        raise NotImplementedError

    def broadcast(self, msg):
        """
        broadcast the given message to all the transports

        Arguments:
            msg (str): message to be broadcasted
        """
        for transport in self.transports:
            transport.broadcast(msg)


class Server(object):
    """
    The emulation server

    Handles a set of devices
    """

    def __init__(self, name='', devices=(), backdoor=None):
        self.name = name
        self._log = logging.getLogger('{0}.{1}'.format(_log.name, name))
        self._log.info('Bootstraping server')
        if backdoor:
            from gevent.backdoor import BackdoorServer
            banner = 'Welcome to Bliss emulator server console.\n' \
                     'My name is {0!r}. You can access me through the ' \
                     '\'server()\' function. Have fun!'.format(name)
            self._log.info('Opening backdoor at %r', backdoor)
            self.backdoor = BackdoorServer(backdoor, banner=banner,
                                           locals=dict(server=weakref.ref(self)))
            self.backdoor.start()
        self.devices = {}
        for device in devices:
            try:
                self.create_device(device)
            except Exception as error:
                dname = device.get('name', device.get('class', 'unknown'))
                self._log.error('error creating device %s (will not be available): %s',
                                dname, error)
                self._log.debug('details: %s', error, exc_info=1)

    def create_device(self, device_info):
        klass_name = device_info.get('class')
        name = device_info.get('name', klass_name)
        self._log.info('Creating device %s (%r)', name, klass_name)
        device, transports = create_device(device_info)
        self.devices[device] = transports
        return device, transports

    def get_device_by_name(self, name):
        for device in self.devices:
            if device.name == name:
                return device

    def start(self):
        for device in self.devices:
            for interface in self.devices[device]:
                interface.start()

    def stop(self):
        for device in self.devices:
            for interface in self.devices[device]:
                interface.stop()

    def serve_forever(self):
        stop_events = []
        for device in self.devices:
            for interface in self.devices[device]:
                stop_events.append(interface._stop_event)
        self.start()
        try:
            gevent.joinall(stop_events)
        finally:
            self.stop()

    def __str__(self):
        return '{0}({1})'.format(self.__class__.__name__, self.name)


def create_device(device_info):
    device_info = dict(device_info)
    class_name = device_info.pop('class')
    module_name = device_info.pop('module', class_name.lower())
    package_name = device_info.pop('package', None)
    name = device_info.pop('name', class_name)

    if package_name is None:
        package_name = 'bliss.controllers.emulators.' + module_name

    __import__(package_name)
    package = sys.modules[package_name]
    klass = getattr(package, class_name)
    device = klass(name, **device_info)

    transports_info = device_info.pop('transports', ())
    transports = []
    for interface_info in transports_info:
        ikwargs = dict(interface_info)
        itype = ikwargs.pop('type', 'tcp')
        if itype == 'tcp':
            iklass = TCPServer
        elif itype == 'serial':
            iklass = SerialServer
        ikwargs['device'] = device
        transports.append(iklass(**ikwargs))
    device.transports = transports
    return device, transports


def create_server_from_config(config, name):
    cfg = config.get_config(name)
    backdoor, devices = cfg.get('backdoor', None), cfg.get('devices', ())
    return Server(name=name, devices=devices, backdoor=backdoor)


def main():
    import argparse
    from bliss.config.static import get_config

    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('name',
                        help='server name as defined in the static configuration')
    parser.add_argument('--log-level', default='WARNING', help='log level',
                        choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'])
    args = parser.parse_args()

    fmt = '%(asctime)-15s %(levelname)-5s %(name)s: %(message)s'
    level = getattr(logging, args.log_level.upper())
    logging.basicConfig(format=fmt, level=level)
    config = get_config()

    server = create_server_from_config(config, args.name)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCtrl-C Pressed. Bailing out...")

if __name__ == "__main__":
    main()
