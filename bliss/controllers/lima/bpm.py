# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy

from bliss.common.utils import grouped
from bliss.common.counter import IntegratingCounter
from bliss.controllers.counter import IntegratingCounterController
from bliss.scanning.acquisition.counter import IntegratingCounterAcquisitionSlave
from bliss.scanning.chain import ChainNode


class LimaBpmCounter(IntegratingCounter):
    """Lima BPM integrating counter."""

    def __init__(self, name, value_index, controller):
        super().__init__(name, controller)
        self.__value_index = value_index

    @property
    def value_index(self):
        return self.__value_index


class BpmChainNode(ChainNode):
    def _get_default_chain_parameters(self, scan_params, acq_params):
        try:
            count_time = acq_params["count_time"]
        except:
            count_time = scan_params["count_time"]

        params = {"count_time": count_time}

        return params

    def get_acquisition_object(self, acq_params, ctrl_params=None):
        # --- Warn user if an unexpected is found in acq_params
        expected_keys = ["count_time"]
        for key in acq_params.keys():
            if key not in expected_keys:
                print(
                    f"=== Warning: unexpected key '{key}' found in acquisition parameters for BPM IntegratingCounterAcquisitionSlave({self.controller}) ==="
                )

        count_time = acq_params["count_time"]
        return IntegratingCounterAcquisitionSlave(
            *self.counters, count_time=count_time, ctrl_params=ctrl_params
        )


class Bpm(IntegratingCounterController):
    def __init__(self, name, bpm_proxy, acquisition_proxy):
        super().__init__(
            "bpm", master_controller=acquisition_proxy, chain_node_class=BpmChainNode
        )
        self._proxy = bpm_proxy
        self._counters.update(
            {
                "acq_time": LimaBpmCounter("acq_time", 0, self),
                "intensity": LimaBpmCounter("intensity", 1, self),
                "x": LimaBpmCounter("x", 2, self),
                "y": LimaBpmCounter("y", 3, self),
                "fwhm_x": LimaBpmCounter("fwhm_x", 4, self),
                "fwhm_y": LimaBpmCounter("fwhm_y", 5, self),
            }
        )

    def prepare(self, *counters):
        self.start()

    def start(self, *counters):
        self._proxy.Start()

    def stop(self, *counters):
        self._proxy.Stop()

    @property
    def acq_time(self):
        return self._counters["acq_time"]

    @property
    def x(self):
        return self._counters["x"]

    @property
    def y(self):
        return self._counters["y"]

    @property
    def intensity(self):
        return self._counters["intensity"]

    @property
    def fwhm_x(self):
        return self._counters["fwhm_x"]

    @property
    def fwhm_y(self):
        return self._counters["fwhm_y"]

    def get_values(self, from_index, *counters):
        # BPM data are : timestamp, intensity, center_x, center_y, fwhm_x, fwhm_y, frameno
        result_size = 7
        all_result = self._proxy.GetResults(from_index)
        nb_result = len(all_result) // result_size
        counter2index = [
            (numpy.zeros((nb_result,)), cnt.value_index) for cnt in counters
        ]

        for i, raw in enumerate(grouped(all_result, result_size)):
            for res, j in counter2index:
                res[i] = raw[j]

        return [x[0] for x in counter2index]
