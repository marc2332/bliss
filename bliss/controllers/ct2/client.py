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

import numpy

from bliss.comm.rpc import Client
from bliss.common.measurement import IntegratingCounter


CT2 = Client


class CT2CounterGroup(IntegratingCounter.GroupedReadHandler):

    def prepare(self, *counters):
        channels = []
        counter_indexes = {}
        ctrl = self.controller
        in_channels = ctrl.INPUT_CHANNELS
        timer_counter = ctrl.internal_timer_counter
        point_nb_counter = ctrl.internal_point_nb_counter
        channel_counters = dict([(counter.channel, counter)
                                 for counter in counters])

        for i, channel in enumerate(sorted(channel_counters)):
            counter = channel_counters[channel]
            if channel in in_channels:
                channels.append(channel)
            elif channel == timer_counter:
                i = -2
                counter.timer_freq = ctrl.timer_freq
            elif channel == point_nb_counter:
                i = -1
            counter_indexes[counter] = i
        ctrl.acq_channels = channels
        # counter_indexes dict<counter: index in data array>
        self.counter_indexes = counter_indexes
        # a hack here: since this prepare is called AFTER the
        # CT2AcquisitionDevice prepare, we do a "second" prepare
        # here after the acq_channels have been configured
        self.controller.prepare_acq()

    def get_values(self, from_index, *counters):
        data = self.controller.get_data(from_index).T
        if not data.size:
            return len(counters) * (numpy.array(()),)
        result = [counter.convert(data[self.counter_indexes[counter]])
                  for counter in counters]
        return result


class CT2Counter(IntegratingCounter):

    def __init__(self, name, channel, **kwargs):
        self.channel = channel
        super(CT2Counter, self).__init__(name, **kwargs)

    def convert(self, data):
        return data

    def __repr__(self):
        return '{0}({1!r}, ch={2})'.format(type(self).__name__, self.name,
                                           self.channel)


class CT2CounterTimer(CT2Counter):

    def __init__(self, name, **kwargs):
        ctrl = kwargs['controller']
        self.timer_freq = ctrl.timer_freq
        super(CT2CounterTimer, self).__init__(
            name, ctrl.internal_timer_counter, **kwargs)

    def convert(self, ticks):
        return ticks / self.timer_freq


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

    if isinstance(config_or_name, basestring):
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
    device.acq_counter_group = CT2CounterGroup(device)

    orig_configure = device.configure

    def configure(device_config):
        orig_configure(device_config)
        for counter_name in device.acq_counters:
            delattr(device, counter_name)
        device.acq_counters = {}
        for channel in device_config.get('channels', ()):
            ct_name = channel.get('counter name', None)
            if ct_name:
                address = int(channel['address'])
                ct = CT2Counter(
                    ct_name, address, controller=device,
                    acquisition_controller=device,
                    grouped_read_handler=device.acq_counter_group)
                device.acq_counters[ct_name] = ct
                setattr(device, ct_name, ct)
        timer = device_config.get('timer', None)
        if timer is not None:
            ct_name = timer.get('counter name', None)
            if ct_name:
                ct = CT2CounterTimer(
                    ct_name, controller=device,
                    acquisition_controller=device,
                    grouped_read_handler=device.acq_counter_group)
                device.acq_counters[ct_name] = ct
                setattr(device, ct_name, ct)

    device.configure = configure
    device.configure(device_config)
    return device


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    device = create_and_configure_device(node)
    return {name: device}, {name: device}
