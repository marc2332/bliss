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

    pass


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
            self.controller,
            *self.counters,
            count_time=count_time,
            ctrl_params=ctrl_params,
        )


class Bpm(IntegratingCounterController):
    def __init__(self, name, bpm_proxy, acquisition_proxy):
        super().__init__(
            "bpm", master_controller=acquisition_proxy, chain_node_class=BpmChainNode
        )
        self._proxy = bpm_proxy
        self._name2index = {
            "acq_time": 0,
            "intensity": 1,
            "x": 2,
            "y": 3,
            "fwhm_x": 4,
            "fwhm_y": 5,
        }
        self._counters.update(
            {
                "acq_time": self.acq_time,
                "x": self.x,
                "y": self.y,
                "intensity": self.intensity,
                "fwhm_x": self.fwhm_x,
                "fwhm_y": self.fwhm_y,
            }
        )

    @property
    def acq_time(self):
        return LimaBpmCounter("acq_time", self)

    @property
    def x(self):
        return LimaBpmCounter("x", self)

    @property
    def y(self):
        return LimaBpmCounter("y", self)

    @property
    def intensity(self):
        return LimaBpmCounter("intensity", self)

    @property
    def fwhm_x(self):
        return LimaBpmCounter("fwhm_x", self)

    @property
    def fwhm_y(self):
        return LimaBpmCounter("fwhm_y", self)

    def prepare(self, *counters):
        self._proxy.On()

    def stop(self, *counters):
        self._proxy.Off()

    def get_values(self, from_index, *counters):
        result_size = self._proxy.ResultSize
        all_result = self._proxy.GetResults(from_index)
        nb_result = len(all_result) / result_size
        counter2index = [
            (numpy.zeros((nb_result,)), self._name2index[cnt.name]) for cnt in counters
        ]

        for i, raw in enumerate(grouped(all_result, result_size)):
            for res, j in counter2index:
                res[i] = raw[j]

        return [x[0] for x in counter2index]
