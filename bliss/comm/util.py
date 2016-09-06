# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Communication tools (:func:`~bliss.comm.util.get_interface`)"""

__all__ = ['get_interface']

from .serial import Serial
from .gpib import Gpib
from .tcp import Tcp

__INTERFACES = dict(serial=Serial, gpib=Gpib, tcp=Tcp)

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
            for iname, iclass in __INTERFACES.items():
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
