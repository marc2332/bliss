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

from bliss.comm.rpc import Client

CT2 = Client

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

    kwargs = {}
    if 'timeout' in device_config:
        kwargs['timeout'] = device_config['timeout']
    device = CT2(device_config['address'], **kwargs)
    device.name = name
    device.acq_counters = {}
    device.acq_counter_group = CounterGroup(device)

    orig_configure = device.configure
    def configure(device_config):
        orig_configure(device_config)
        device.acq_counters = {}
        for channel in device_config.get('channels', ()):
            ct_name = channel.get('counter name', None)
            if ct_name:
                address = int(channel['address'])
                ct = Counter(ct_name, address, controller=device,
                             acquisition_controller=device,
                             grouped_read_handler=device.acq_counter_group)
                device.acq_counters[ct_name] = ct
        timer = device_config.get('timer', None)
        if timer is not None:
            ct_name = timer.get('counter name', None)
            if ct_name:
                ct = CounterTimer(ct_name, controller=device,
                                  acquisition_controller=device,
                                  grouped_read_handler=device.acq_counter_group)
                device.acq_counters[ct_name] = ct
    device.configure = configure
    device.configure(device_config)
    return device


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    device = create_and_configure_device(node)
    return {name:device}, {name:device}
