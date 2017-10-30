# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
CT2 (P201/C208) ESRF PCI counter card device

Minimalistic configuration example:

.. code-block:: yaml

   plugin: ct2
   name: p201
   class: CT2
   address: tcp://lid312:8909


(for the complete CT2 YAML_ specification see :ref:`bliss-ct2-yaml`)
"""

import inspect

import gevent
import zerorpc
import msgpack_numpy

from . import device
from bliss.common.event import dispatcher

msgpack_numpy.patch()


def __create_property(name, member):
    def fget(self):
        return self.get_property(name)
    def fset(self, value):
        self.set_property(name, value)
    return property(fget, fset, doc=member.__doc__)


def __fill_properties(this, klass):
    # Workaround to create property access on this class since
    # RPC only supports method calls.
    # This adds to *this* the same properties as *klass*.
    # Each property getter/setter will call RPC *get/set_property*
    for name, member in inspect.getmembers(klass):
        if name.startswith('_') or not inspect.isdatadescriptor(member):
            continue
        setattr(this, name, __create_property(name, member))
    return this


class CT2(zerorpc.Client):

    def connect(self, *args, **kwargs):
        super(CT2, self).connect(*args, **kwargs)
        self.__events_task = gevent.spawn(self.__dispatch_events)

    def close(self):
        self.__events_task.kill()
        super(CT2, self).close()

    def __dispatch_events(self):
        events = self.events()
        for event in events:
            dispatcher.send(event[0], self, event[1])



__fill_properties(CT2, device.CT2)


def __get_device_config(name):
    from bliss.config.static import get_config
    config = get_config()
    device_config = config.get_config(name)
    return device_config


def create_and_configure_device(config_or_name):
    """
    Create a device from the given configuration (beacon compatible) or its
    configuration name.

    Args:
        config_or_name: (config or name: configuration dictionary (or
                        dictionary like object) or configuration name
    Returns:
        a new instance of :class:`CT2` configured and ready to go
    """

    if isinstance(config_or_name, (str, unicode)):
        device_config = __get_device_config(config_or_name)
        name = config_or_name
    else:
        device_config = config_or_name
        name = device_config['name']

    timeout = device_config.get('timeout', 1)
    device = CT2(device_config['address'], timeout=timeout)
    device.configure(device_config)
    return device


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    device = create_and_configure_device(node)
    return {name:device}, {name:device}
