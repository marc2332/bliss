# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from bliss.common.measurement import IntegratingCounter
from bliss.common.utils import grouped


class _GroupReadHandler(IntegratingCounter.GroupedReadHandler):
    def __init__(self, controller):
        IntegratingCounter.GroupedReadHandler.__init__(self, controller)

    def prepare(self, *counters):
        self.controller._proxy.On()

    def end(self, *counters):
        self.controller._proxy.Off()

    def get_values(self, from_index, *counters):
        result_size = self.controller._proxy.ResultSize
        all_result = self.controller._proxy.GetResults(from_index)
        nb_result = len(all_result) / result_size
        counter2index = [
            (numpy.zeros((nb_result,)), self.controller._name2index[cnt.name])
            for cnt in counters
        ]

        for i, raw in enumerate(grouped(all_result, result_size)):
            for res, j in counter2index:
                res[i] = raw[j]

        return [x[0] for x in counter2index]


class LimaBpmCounter(IntegratingCounter):
    """Lima BPM integrating counter."""

    pass


class Bpm(object):
    def __init__(self, name, bpm_proxy, acquisition_proxy):
        self.name = "bpm"
        self._proxy = bpm_proxy
        self._acquisition_proxy = acquisition_proxy
        self._name2index = {
            "acq_time": 0,
            "intensity": 1,
            "x": 2,
            "y": 3,
            "fwhm_x": 4,
            "fwhm_y": 5,
        }
        self._grouped_read_handler = _GroupReadHandler(self)

    @property
    def acq_time(self):
        return LimaBpmCounter(
            "acq_time",
            self,
            self._acquisition_proxy,
            grouped_read_handler=self._grouped_read_handler,
        )

    @property
    def x(self):
        return LimaBpmCounter(
            "x",
            self,
            self._acquisition_proxy,
            grouped_read_handler=self._grouped_read_handler,
        )

    @property
    def y(self):
        return LimaBpmCounter(
            "y",
            self,
            self._acquisition_proxy,
            grouped_read_handler=self._grouped_read_handler,
        )

    @property
    def intensity(self):
        return LimaBpmCounter(
            "intensity",
            self,
            self._acquisition_proxy,
            grouped_read_handler=self._grouped_read_handler,
        )

    @property
    def fwhm_x(self):
        return LimaBpmCounter(
            "fwhm_x",
            self,
            self._acquisition_proxy,
            grouped_read_handler=self._grouped_read_handler,
        )

    @property
    def fwhm_y(self):
        return LimaBpmCounter(
            "fwhm_y",
            self,
            self._acquisition_proxy,
            grouped_read_handler=self._grouped_read_handler,
        )

    @property
    def counters(self):
        return [self.acq_time, self.x, self.y, self.intensity, self.fwhm_x, self.fwhm_y]
