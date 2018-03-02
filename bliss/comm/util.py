# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Communication tools (:func:`~bliss.comm.util.get_interface`,
:func:`~bliss.comm.util.HexMsg`)"""

__all__ = ['get_interface', 'get_comm_type', 'get_comm', 'HexMsg',
           'TCP', 'SERIAL', 'GPIB', 'UDP']

TCP, SERIAL, GPIB, UDP = 'tcp', 'serial', 'gpib', 'udp'


def get_interface(*args, **kwargs):
    """
    Create a communication interface from args, kwargs.

    If *interface* keyword argument is given, it is used and returned. All
    other arguments and keyword arguments are returned as not interpreted.

    Else, if *args* are given, first argument it is interpreted as *interface*.
    All other arguments and keyword arguments are returned as not interpreted.

    Otherwise, it expects either a *serial*, *gpib* or *tcp* keyword argument.
    The value should be a dictionary which is the same that would be passed
    directly to the corresponding class constructor. An new interface
    (:class:`~bliss.comm.serial.Serial`, :class:`~bliss.comm.gpib.Gpib` or
    :class:`~bliss.comm.tcp.Tcp`) is created and returned.

    Useful to use in an `__init__` to parse arguments and keyword arguments
    with interface connection. Example of usage::

        from ... import BaseDevice
        from bliss.comm.util import get_interface

        class Lecroy(BaseDevice):

            def __init__(self, *args, **kwargs):
                interface, args, kwargs = get_interface(*args, **kwargs)
                self.interface = interface
                super(Lecroy, self).__init__(*args, **kwargs)

    Returns:
        (interface, args, kwargs): the interface, args and kwargs are the non
        interpreted arguments.

    """
    if 'interface' in kwargs:
        interface = kwargs.pop('interface')
    else:
        if args:
            interface, args = args[0], args[1:]
        else:
            from .tcp import Tcp
            from .gpib import Gpib
            from .serial import Serial
            from .udp import Udp
            interfaces = dict(serial=Serial, gpib=Gpib, tcp=Tcp, udp=Udp)
            for iname, iclass in interfaces.items():
                if iname in kwargs:
                    ikwargs = kwargs.pop(iname)
                    if isinstance(ikwargs, dict):
                        interface = iclass(**ikwargs)
                    else:
                        interface = ikwargs
                    break
            else:
                raise RuntimeError("Cannot find proper interface")
    return interface, args, kwargs


def get_comm_type(config):
    """
    Returns the communication channel type from the given configuration.
    Expects a dict like config object. It recognizes keywords: *tcp*, *gpib* or
    *serial*.

    Args:
       config (dict): a dict like config object which contains communication
                      channel configuration
    Returns:
        ``TCP``, ``GPIB`` , ``SERIAL`` or ``UDP``
    Raises:
        ValueError: if no communication channel or more than one communication
                    channel is found in config
    """
    comm_type = None
    if 'tcp-proxy' in config:
        config = config.get('tcp-proxy')

    if 'tcp' in config:
        comm_type = TCP
    if 'gpib' in config:
        if comm_type:
            raise ValueError('More than one communication channel found')
        comm_type = GPIB
    if 'serial' in config:
        if comm_type:
            raise ValueError('More than one communication channel found')
        comm_type = SERIAL
    if 'udp' in config:
        if comm_type:
            raise ValueError('More than one communication channel found')
        comm_type = UDP
    if comm_type is None:
        raise ValueError('No communication channel found in config')
    return comm_type


def get_comm(config, ctype=None, **opts):
    """
    Expects a dict like config object. It recognizes keywords: *tcp*, *gpib* or
    *serial*.

    *\*\*opts* represent default values.

    * If *tcp* is given, it must have *url* keyword. *url* must be either
      ```[<host> [, <port>] ]``` or ```"<host>[:<port>]"```. *port* is optional
      if supplied in *\*\*opts*. All other parameters are the same as in the
      :class:`~bliss.comm.tcp.Tcp`:class:`~bliss.comm.tcp.Tcp` class.
    * If *gpib* is given, it must have *url* keyword. *url* is as in
      :class:`~bliss.comm.gpib.Gpib` as well as all other gpib parameters.
    * If *serial* is given, it must have *url* keyword. *url* is as in *port*
      :class:`~bliss.comm.serial.Serial` as well as all other gpib parameters.

    Args:
       config (dict): a dict like config object which contains communication
                      channel configuration
       ctype: expected communication channel type. Valid values are:
              None (means any type), TCP, SERIAL or GPIB  [default: None]
       **opts: default values to use if not present in config
    Returns:
       A Tcp, Gpib or Serial line object
    Raises:
        ValueError: if no communication channel or more than one communication
                    channel is found in config
        KeyError: if there are missing mandatory parameters in the communication
                  channel config (ex: *url*)
        TypeError: if the communication channel type in config does not match
                   the one given by *ctype* argument
    """
    comm_type = get_comm_type(config)
    if ctype is not None and ctype != comm_type:
        raise TypeError('Expected {0!r} communication channel. Got {1!r}'
                        .format(ctype, comm_type))
    klass = None
    if 'tcp-proxy' in config:
        proxy_config = config['tcp-proxy']
        config = proxy_config
    else:
        proxy_config = None

    if comm_type == TCP or comm_type == UDP:
        default_port = opts.pop('port', None)
        opts.update(config[comm_type])
        url = opts['url']
        if isinstance(url, (str, unicode)):
            url = url.rsplit(':', 1)
        if len(url) == 1:
            if default_port is None:
                raise KeyError('Cannot create %s object without port' % comm_type.upper())
            url.append(default_port)
        opts['url'] = '{0[0]}:{0[1]}'.format(url)
        if comm_type == TCP:
            from .tcp import Tcp as klass
        else:
            from .udp import Udp as klass
    elif comm_type == GPIB:
        opts.update(config['gpib'])
        from .gpib import Gpib as klass
    elif comm_type == SERIAL:
        opts.update(config['serial'])
        opts['port'] = opts.pop('url')
        from .serial import Serial as klass
    if klass is None:
        # should not happen (get_comm_type should handle all errors)
        raise ValueError('No communication channel found in config')

    if proxy_config is None:
        return klass(**opts)
    else:
        from .tcp_proxy import Proxy
        return Proxy(proxy_config)


class HexMsg:
    """
    Encapsulate a message with a hexadecimal representation.
    Useful to have in log messages since it only computes the hex representation
    if the log message is recorded. Example::

        import logging
        from bliss.comm.util import HexMsg

        logging.basicConfig(level=logging.INFO)

        msg_from_socket = '\x00\x00\x00\x021\n'
        logging.debug('Rx: %r', HexMsg(msg_from_socket))
    """
    __slots__ = ['msg']

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return ' '.join(map(hex, map(ord, self.msg)))

    def __repr__(self):
        return '[{0}]'.format(self)
