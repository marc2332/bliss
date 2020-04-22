# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Module to manage scan with automatic filter.

Yaml config may look like this:
- plugin: bliss
  class: AutoFilter
  name: autof
  package: bliss.common.auto_filter
  max_nb_iter: 2
  monitor_counter_name: diode
  min_count_rate: 0
  max_count_rate: 10
"""

import weakref
from tabulate import tabulate
from bliss.config.beacon_object import BeaconObject
from bliss.common import scans
from bliss.scanning import chain, scan
from bliss.common.event import dispatcher
from bliss.common.measurementgroup import _get_counters_from_names
from bliss.common.measurementgroup import get_active as get_active_mg
from . import acquisition_objects


class AutoFilter(BeaconObject):
    max_nb_iter = BeaconObject.property_setting(
        "max_nb_iter", must_be_in_config=True, doc="Max iteration on the same point"
    )
    monitor_counter_name = BeaconObject.property_setting(
        "monitor_counter_name", must_be_in_config=True, doc="Monitor counter name"
    )
    min_count_rate = BeaconObject.property_setting(
        "min_count_rate",
        must_be_in_config=True,
        doc="Minimum allowed count rate on monitor",
    )
    max_count_rate = BeaconObject.property_setting(
        "max_count_rate",
        must_be_in_config=True,
        doc="Maximum allowed count rate on monitor",
    )

    def __init__(self, name, config):
        super().__init__(config, share_hardware=False)

        # check a filterset is in config
        self.filterset = config.get("filterset")

    def ascan(self, motor, start, stop, intervals, count_time, *counter_args, **kwargs):
        """
        Basically same as normal ascan with auto filter management
        """

        save_flag = kwargs.get("save", True)
        programed_device_intervals = (intervals + 1) * self.max_nb_iter
        npoints = intervals + 1
        scan_pars = {
            "type": "ascan",
            "npoints": programed_device_intervals,
            "count_time": count_time,
            "sleep_time": kwargs.get("sleep_time"),
            "save": save_flag,
        }

        monitor_counter_name = self.monitor_counter_name
        counters, missing = _get_counters_from_names([monitor_counter_name])
        if missing:
            raise RuntimeError(
                f"Can't find monitor counter named {monitor_counter_name}"
            )
        monitor_counter = counters[0]

        if not counter_args:  # use the default measurement group
            counter_args = [get_active_mg()] + [monitor_counter]
        else:
            counter_args = list(counter_args) + [monitor_counter]
        default_chain = scans.DEFAULT_CHAIN.get(scan_pars, counter_args)
        final_chain, monitor_channel = self._patch_chain(
            default_chain, npoints, monitor_counter
        )
        # cache min and max count-rate
        min_count_rate = self.min_count_rate
        max_count_rate = self.max_count_rate

        class Validator:
            def __init__(self, autofilter):
                self.__autofilter = weakref.proxy(autofilter)
                self._point_nb = 0
                dispatcher.connect(self.new_monitor_value, "new_data", monitor_channel)

            def new_monitor_value(self, event_dict=None, signal=None, sender=None):
                data = event_dict.get("data")
                if data is not None:
                    valid = True
                    if data > max_count_rate:
                        self.__autofilter.incr_filter(
                            data, min_count_rate, max_count_rate
                        )
                        valid = False
                    elif data < min_count_rate:
                        self.__autofilter.decr_filter(
                            data, min_count_rate, max_count_rate
                        )
                        valid = False
                    for node in final_chain.nodes_list:
                        if hasattr(node, "validate_point"):
                            node.validate_point(self._point_nb, valid)
                    self._point_nb += 1

        validator = Validator(self)
        top_master = acquisition_objects.LinearStepTriggerMaster(
            npoints, motor, start, stop
        )
        timer = final_chain.top_masters.pop(0)
        final_chain.add(top_master, timer)
        s = scan.Scan(
            final_chain,
            scan_info=scan_pars,
            name=kwargs.setdefault("name", "ascan"),
            save=kwargs.get("save", True),
            save_images=kwargs.get("save_images"),
            data_watch_callback=scan.StepScanDataWatch(),
        )
        if kwargs.get("run", True):
            s.run()
        return s

    def _patch_chain(self, default_chain, npoints, monitor_counter):
        final_chain = chain.AcquisitionChain(parallel_prepare=True)
        monitor_channel = None
        # use the built **default_chain** and replace all
        # acquisition object with autofilter one.
        for master in (
            x
            for x in default_chain._tree.expand_tree()
            if isinstance(x, chain.AcquisitionMaster)
        ):
            final_master = acquisition_objects.get_new_master(self, master, npoints)
            for slave in default_chain._tree.get_node(master).fpointer:
                final_slave = acquisition_objects.get_new_slave(self, slave, npoints)
                final_chain.add(final_master, final_slave)
                if monitor_channel is None:
                    for channel in slave.channels:
                        if channel.fullname == monitor_counter.fullname:
                            monitor_channel = channel
                            break
        return final_chain, monitor_channel

    def __info__(self):
        table_info = []
        for sname in (
            "max_nb_iter",
            "monitor_counter_name",
            "min_count_rate",
            "max_count_rate",
            "always_back",
        ):
            table_info.append([sname, getattr(self, sname)])
        info = str(tabulate(table_info, headers=["Parameter", "Value"]))
        info += "\n\n" + f"Active filterset: {self.filterset.name}"
        info += (
            "\n"
            + f"Energy axis {self.energy_axis.name}: {self.energy_axis.position:.5g} keV"
        )
        # info += "\n" + self.filterset.__info__()
        info += "\n\n" + f"Active filter idx {self.filterset.filter}"
        info += "\n\n" + "Table of Effective Filters :"
        info += "\n" + self.filterset.info_table()
        return info

    def incr_filter(self, value, min_count_rate, max_count_rate):
        """
        Function to increment the filter level
        value -- measure data
        max_count_rate -- maximum authorize value
        """
        self.filterset.incr_filter(value, min_count_rate, max_count_rate)

    def decr_filter(self, value, min_count_rate, max_count_rate):
        """
        Function to decrement the filter level
        value -- measure data
        min_count_rate -- minimum authorize value
        """
        self.filterset.decr_filter(value, min_count_rate, max_count_rate)
