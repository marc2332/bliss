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
from bliss.scanning.acquisition.lima import BpmAcquisitionSlave


class LimaBpmCounter(IntegratingCounter):
    """Lima BPM integrating counter."""

    def __init__(self, name, value_index, controller):
        super().__init__(name, controller)
        self.__value_index = value_index

    @property
    def value_index(self):
        return self.__value_index


class Bpm(IntegratingCounterController):
    def __init__(self, name, bpm_proxy, acquisition_proxy):
        # leave counters registration to the parent object
        super().__init__(
            "bpm", master_controller=acquisition_proxy, register_counters=False
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

    def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
        if "acq_expo_time" in parent_acq_params:
            acq_params.setdefault("count_time", parent_acq_params["acq_expo_time"])
        if "acq_nb_frames" in parent_acq_params:
            acq_params.setdefault("npoints", parent_acq_params["acq_nb_frames"])

        return BpmAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

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
