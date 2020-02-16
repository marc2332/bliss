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

import functools
import numpy
from bliss.common.proxy import Proxy

from bliss.comm.rpc import Client
from bliss.common.counter import IntegratingCounter

from bliss import global_map

from bliss.controllers.ct2.device import AcqMode
from bliss.controllers.counter import CounterController
from bliss.controllers.counter import IntegratingCounterController


class CT2Counter(IntegratingCounter):
    def __init__(self, name, channel, controller):
        self.channel = channel
        super().__init__(name, controller)

    def convert(self, data):
        return data

    def __repr__(self):
        return "{0}({1!r}, ch={2})".format(type(self).__name__, self.name, self.channel)


class CT2CounterTimer(CT2Counter):
    def __init__(self, name, controller):
        self.timer_freq = controller._master_controller.timer_freq
        super(CT2CounterTimer, self).__init__(
            name, controller._master_controller.internal_timer_counter, controller
        )

    def convert(self, ticks):
        return ticks / self.timer_freq


class CT2Controller(Proxy, CounterController):
    def __init__(self, device_config, name="ct2_cc", **kwargs):

        board_address = device_config["address"]

        Proxy.__init__(
            self, functools.partial(Client, board_address, **kwargs), init_once=True
        )

        CounterController.__init__(self, name=name, register_counters=False)

        global_map.register(self, children_list=[self.__wrapped__])

        # Remote call
        self.configure(device_config)

        slave = CT2CounterController("ct2_counters_controller", self)

        # Add ct2 counters
        for channel in device_config.get("channels", ()):
            ct_name = channel.get("counter name", None)
            if ct_name:
                address = int(channel["address"])
                slave.create_counter(CT2Counter, ct_name, address)
        # Add ct2 counter timer
        timer = device_config.get("timer", None)
        if timer is not None:
            ct_name = timer.get("counter name", None)
            if ct_name:
                slave.create_counter(CT2CounterTimer, ct_name)

        self._counters = slave._counters
        self.board_address = board_address

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):

        from bliss.scanning.acquisition.ct2 import CT2AcquisitionMaster

        return CT2AcquisitionMaster(self, ctrl_params=ctrl_params, **acq_params)

    def get_default_chain_parameters(self, scan_params, acq_params):
        # Extract scan parameters
        try:
            npoints = acq_params["npoints"]
        except KeyError:
            npoints = scan_params.get("npoints", 1)

        try:
            acq_expo_time = acq_params["acq_expo_time"]
        except KeyError:
            acq_expo_time = scan_params["count_time"]

        acq_point_period = acq_params.get("acq_point_period")
        acq_mode = acq_params.get("acq_mode", AcqMode.IntTrigMulti)
        prepare_once = acq_params.get("prepare_once", True)
        start_once = acq_params.get("start_once", True)

        params = {}
        params["npoints"] = npoints
        params["acq_expo_time"] = acq_expo_time
        params["acq_point_period"] = acq_point_period
        params["acq_mode"] = acq_mode
        params["prepare_once"] = prepare_once
        params["start_once"] = start_once

        return params

    def __info__(self):
        infos = f"CT2Controller [address={self.board_address}]\n"
        infos += "Counters:\n"
        for name, cnt in self._counters.items():
            infos += f"  channel {cnt.channel:2d} : {name}"
            if cnt.channel == self.internal_timer_counter:
                infos += " [timer]"
            infos += "\n"
        infos += "External signals:\n"
        if self.input_channel is not None:
            infos += f"  input channel  : {self.input_channel}\n"
        else:
            infos += f"  input channel  : Not Configured\n"
        if self.output_channel is not None:
            infos += f"  output channel : {self.output_channel}\n"
        else:
            infos += f"  output channel  : Not Configured\n"
        return infos


class CT2CounterController(IntegratingCounterController):
    def __init__(self, name, master_controller):
        super().__init__(name=name, master_controller=master_controller)

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        from bliss.scanning.acquisition.ct2 import CT2CounterAcquisitionSlave

        if "count_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "npoints" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["npoints"])

        return CT2CounterAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    def get_values(self, from_index, *counters):
        data = self._master_controller.get_data(from_index).T
        if not data.size:
            return len(counters) * (numpy.array(()),)
        result = [
            counter.convert(data[self.counter_indexes[counter]]) for counter in counters
        ]
        return result


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

    if isinstance(config_or_name, str):
        device_config = __get_device_config(config_or_name)
        name = config_or_name
    else:
        device_config = config_or_name
        name = device_config["name"]

    kwargs = {}
    if "timeout" in device_config:
        kwargs["timeout"] = device_config["timeout"]

    acq_ctrl = CT2Controller(device_config, name, **kwargs)

    return acq_ctrl


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    device = create_and_configure_device(node)
    return {name: device}, {name: device}
