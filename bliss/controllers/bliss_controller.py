# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import enum
from time import perf_counter, sleep
from itertools import chain
from collections import ChainMap
from gevent import Timeout, event, sleep as gsleep

from bliss import global_map
from bliss.common.protocols import CounterContainer
from bliss.common.counter import Counter, CalcCounter, SamplingCounter
from bliss.common.protocols import counter_namespace
from bliss.common.utils import autocomplete_property
from bliss.comm.util import get_comm
from bliss.controllers.counter import (
    CounterController,
    SamplingCounterController,
    IntegratingCounterController,
)
from bliss.scanning.acquisition.counter import BaseCounterAcquisitionSlave

from bliss.config.beacon_object import BeaconObject

from bliss.common.logtools import log_info, log_debug, log_debug_data, log_warning


class HardwareController:
    def __init__(self, config):
        self._config = config
        self._last_cmd_time = perf_counter()
        self._cmd_min_delta_time = 0

        self._init_com()

    @property
    def config(self):
        return self._config

    @property
    def comm(self):
        return self._comm

    def send_cmd(self, cmd, *values):
        now = perf_counter()
        log_info(self, f"@{now:.3f} send_cmd", cmd, values)
        if self._cmd_min_delta_time:
            delta_t = now - self._last_cmd_time
            if delta_t < self._cmd_min_delta_time:
                sleep(self._cmd_min_delta_time - delta_t)

        return self._send_cmd(cmd, *values)

    def _send_cmd(self, cmd, *values):
        if values:
            return self._write_cmd(cmd, *values)
        else:
            return self._read_cmd(cmd)

    def _init_com(self):
        log_info(self, "_init_com", self.config)
        self._comm = get_comm(self.config)
        global_map.register(self._comm, parents_list=[self, "comms"])

    # ========== NOT IMPLEMENTED METHODS ====================
    def _write_cmd(self, cmd, *values):
        # return self._comm.write(cmd, *values)
        raise NotImplementedError

    def _read_cmd(self, cmd):
        # return self._comm.read(cmd)
        raise NotImplementedError


class BlissController(CounterContainer):

    COUNTER_TAGS = {}

    def __init__(self, name, config):

        self._name = name
        self._config = config

        self._counter_controllers = {}
        self._hw_controller = None

        self._load_config()
        self._build_axes()
        self._build_counters()

    @autocomplete_property
    def hw_controller(self):
        if self._hw_controller is None:
            self._hw_controller = self._get_hardware()
        return self._hw_controller

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return self._config

    # ========== NOT IMPLEMENTED METHODS ====================
    def _get_hardware(self):
        """ Must return an HardwareController object """
        raise NotImplementedError

    def _load_config(self):
        """ Read and apply the YML configuration """
        raise NotImplementedError

    def _build_counters(self):
        """ Build the CounterControllers and associated Counters"""
        raise NotImplementedError

    def _build_axes(self):
        """ Build the Axes (real and pseudo) """
        raise NotImplementedError

    @property
    def counters(self):
        # cnts = [ctrl.counters for ctrl in self._counter_controllers.values()]
        # return counter_namespace(chain(*cnts))
        raise NotImplementedError

    @property
    def axes(self):
        # axes = [ctrl.axes for ctrl in self._axis_controllers]
        # return dict(ChainMap(*axes))
        raise NotImplementedError



# ========== MOCKUP CLASSES ==============================


class HCMockup(HardwareController):
    class FakeCom:
        def __init__(self, config):
            pass

        def read(self, cmd):
            return 69

        def write(self, cmd, *values):
            print("HCMockup write", cmd, values)
            return True

    def _init_com(self):
        log_info(self, "_init_com", self.config)
        self._comm = HCMockup.FakeCom(self.config)
        global_map.register(self._comm, parents_list=[self, "comms"])

    def _write_cmd(self, cmd, *values):
        return self._comm.write(cmd, *values)

    def _read_cmd(self, cmd):
        return self._comm.read(cmd)


class BCMockup(BlissController):

    COUNTER_TAGS = {
        "current_temperature": ("cur_temp_ch1", "scc"),
        "integration_time": ("int_time", "icc"),
    }

    def _get_hardware(self):
        """ Must return an HardwareController object """
        return HCMockup(self.config["com"])

    def _load_config(self):
        """ Read and apply the YML configuration """
        print("load config", self.config)

    def _build_counters(self):
        """ Build the CounterControllers and associated Counters"""
        self._counter_controllers["scc"] = BCSCC("scc", self)
        self._counter_controllers["scc"].max_sampling_frequency = self.config.get(
            "max_sampling_frequency", 1
        )

        for cfg in self.config.get("counters"):
            name = cfg["name"]
            tag = cfg["tag"]
            mode = cfg.get("mode")
            unit = cfg.get("unit")
            convfunc = cfg.get("convfunc")

            if self.COUNTER_TAGS[tag][1] == "scc":
                cnt = self._counter_controllers["scc"].create_counter(
                    SamplingCounter, name, unit=unit, mode=mode
                )

                cnt.tag = tag

    def _build_axes(self):
        """ Build the Axes (real and pseudo) """
        # raise NotImplementedError
        pass

    @property
    def counters(self):
        cnts = [ctrl.counters for ctrl in self._counter_controllers.values()]
        return counter_namespace(chain(*cnts))

    @property
    def axes(self):
        # axes = [ctrl.axes for ctrl in self._axis_controllers]
        # return dict(ChainMap(*axes))
        # raise NotImplementedError
        return counter_namespace({})


class BCSCC(SamplingCounterController):
    def __init__(self, name, bctrl):
        super().__init__(name)
        self.bctrl = bctrl

    def read_all(self, *counters):
        values = []
        for cnt in counters:
            tag_info = self.bctrl.COUNTER_TAGS.get(cnt.tag)
            if tag_info:
                values.append(self.bctrl.hw_controller.send_cmd(tag_info[0]))
            else:
                # returned number of data must be equal to the length of '*counters'
                # so raiseError if one of the received counter is not handled
                raise ValueError(f"Unknown counter {cnt} with tag {cnt.tag} !")
        return values


# class BCICC(IntegratingCounterController):
#     def __init__(self, name, bctrl):
#         super().__init__(name)
#         self.bctrl = bctrl

#     def get_values(self, from_index, *counters):


# class BCICC(CounterController):
#     def __init__(self, name, bctrl):
#         super().__init__(name)
#         self.bctrl = bctrl

#     def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
#         return BCIAS(self, ctrl_params=ctrl_params, **acq_params)

#     def get_default_chain_parameters(self, scan_params, acq_params):

#         try:
#             count_time = acq_params["count_time"]
#         except KeyError:
#             count_time = scan_params["count_time"]

#         try:
#             npoints = acq_params["npoints"]
#         except KeyError:
#             npoints = scan_params["npoints"]

#         params = {"count_time": count_time, "npoints": npoints}

#         return params

#     def read_counts(self):
#         """ returns status, nremain, ntotal, time, counts """
#         return self.bctrl.hw_controller.send_cmd()


# class BCIAS(BaseCounterAcquisitionSlave):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self._reading_event = event.Event()

#     def prepare(self):
#         pass

#     def start(self):
#         self._stop_flag = False
#         self._reading_event.clear()

#     def stop(self):
#         self._stop_flag = True
#         self._reading_event.set()
#         if not self.device.counter_is_ready:
#             self.device.counting_stop()

#     def trigger(self):
#         self.device.counting_start(self.count_time)
#         gsleep(self.count_time)
#         self._reading_event.set()

#     def reading(self):
#         self._reading_event.wait()
#         self._reading_event.clear()
#         with Timeout(2.0):
#             while not self._stop_flag:
#                 status, nremain, ntotal, ctime, counts = self.device.read_counts()
#                 if status == "D":
#                     self._emit_new_data([[counts]])
#                     break
#                 else:
#                     gevent.sleep(0.001)
