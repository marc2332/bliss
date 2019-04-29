# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
from bliss.common.measurement import IntegratingCounter, counter_namespace


class CT2CounterGroup(IntegratingCounter.GroupedReadHandler):
    def prepare(self, *counters):
        channels = []
        counter_indexes = {}
        ctrl = self.controller
        in_channels = ctrl.INPUT_CHANNELS
        timer_counter = ctrl.internal_timer_counter
        point_nb_counter = ctrl.internal_point_nb_counter
        channel_counters = dict([(counter.channel, counter) for counter in counters])

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
        ctrl.prepare_acq()

    def get_values(self, from_index, *counters):
        data = self.controller.get_data(from_index).T
        if not data.size:
            return len(counters) * (numpy.array(()),)
        result = [
            counter.convert(data[self.counter_indexes[counter]]) for counter in counters
        ]
        return result


class CT2Counter(IntegratingCounter):
    def __init__(self, name, channel, master_controller, grouped_read_handler):
        self.channel = channel
        super(CT2Counter, self).__init__(
            name,
            grouped_read_handler,
            master_controller=master_controller,
            grouped_read_handler=grouped_read_handler,
        )

    def convert(self, data):
        return data

    def __repr__(self):
        return "{0}({1!r}, ch={2})".format(type(self).__name__, self.name, self.channel)


class CT2CounterTimer(CT2Counter):
    def __init__(self, name, master_controller, grouped_read_handler):
        self.timer_freq = master_controller.timer_freq
        super(CT2CounterTimer, self).__init__(
            name,
            master_controller.internal_timer_counter,
            master_controller=master_controller,
            grouped_read_handler=grouped_read_handler,
        )

    def convert(self, ticks):
        return ticks / self.timer_freq


def __get_device_config(name):
    from bliss.config.static import get_config

    config = get_config()
    device_config = config.get_config(name)
    return device_config


def configure(device, device_config):
    # Remote call
    device._orig_configure(device_config)
    counters = []
    # Add ct2 counters
    for channel in device_config.get("channels", ()):
        ct_name = channel.get("counter name", None)
        if ct_name:
            address = int(channel["address"])
            counters.append(
                CT2Counter(
                    ct_name,
                    address,
                    master_controller=device,
                    grouped_read_handler=device.acq_counter_group,
                )
            )
    # Add ct2 counter timer
    timer = device_config.get("timer", None)
    if timer is not None:
        ct_name = timer.get("counter name", None)
        if ct_name:
            counters.append(
                CT2CounterTimer(
                    ct_name,
                    master_controller=device,
                    grouped_read_handler=device.acq_counter_group,
                )
            )
    # Set namespace
    device.counters = counter_namespace(counters)


def create_master_device(controller, scan_pars, **settings):
    # Break import cycles
    from bliss.scanning.acquisition.ct2 import CT2AcquisitionMaster

    # Extract scan parameters
    npoints = scan_pars.get("npoints", 1)
    acq_expo_time = scan_pars["count_time"]

    # Create master
    return CT2AcquisitionMaster(
        controller, npoints=npoints, acq_expo_time=acq_expo_time, **settings
    )


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

    if isinstance(config_or_name, str):
        device_config = __get_device_config(config_or_name)
        name = config_or_name
    else:
        device_config = config_or_name
        name = device_config["name"]

    kwargs = {}
    if "timeout" in device_config:
        kwargs["timeout"] = device_config["timeout"]
    device = Client(device_config["address"], **kwargs)

    device.name = name
    device.acq_counter_group = CT2CounterGroup(device)

    device._orig_configure = device.configure
    device.configure = configure.__get__(device, type(device))
    device.create_master_device = create_master_device.__get__(device, type(device))

    device.configure(device_config)
    return device


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    device = create_and_configure_device(node)
    return {name: device}, {name: device}
