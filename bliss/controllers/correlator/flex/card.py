# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

__all__ = ["Card"]

import ctypes
import enum
import weakref
from collections import namedtuple
import numpy
import gevent

from bliss.config.settings import HashObjSetting
from bliss.config.channels import Cache

MODE = enum.Enum("MODE", "SINGLE_AUTO SINGLE_CROSS " "DUAL_AUTO DUAL_CROSS QUAD")
_MODE_STRUCT = namedtuple("AcqMode", "init start")


class Card(object):
    MODE = MODE
    ENUM_2_ACQ = {
        e: _MODE_STRUCT(ctypes.c_byte(ord(i)), s)
        for e, (i, s) in list(
            zip(MODE, (("A", 0), ("A", 1), ("B", 0), ("B", 1), ("C", 0)))
        )
    }

    FLEX_TIME = 0.052428799999999999999999999999547
    FLEX_DELAY = 1E-6 / 640
    """
    Low level interface to control Flex correlator device
    """

    def __init__(self, name, low_level_library="flex02-01d.dll"):
        self._name = name
        self._parameters = HashObjSetting(
            "%s:parameters" % name, default_values={"mode": Card.MODE.SINGLE_AUTO}
        )
        self._run_flag = Cache(self, "run_flag", default_value=False)
        self._lib = ctypes.CDLL(low_level_library)
        self._init = False
        self._read_task = None
        self._init_variables()

    def _init_variables(self):
        self._acq_time = ctypes.c_double(0.)
        self._traceA = list()
        self._traceB = list()
        self._rawcorr = numpy.zeros(1248, dtype=numpy.double)
        self._baseA = numpy.zeros(1248, dtype=numpy.double)
        self._baseB = numpy.zeros(1248, dtype=numpy.double)
        self._sample = numpy.zeros(1120, dtype=numpy.double)

    def _init_lib(self):
        if self._init is False:
            mode = self._parameters["mode"]
            acq_struct = Card.ENUM_2_ACQ[mode]
            if not self._lib._USBInitialize(acq_struct.init):
                raise RuntimeError(
                    "Can not initialize correlator " " to mode **%s**" % str(mode)
                )
            self._init = True

    def __del__(self):
        self.stop_acquisition()
        if self._init:
            self._lib._USBFree()

    @property
    def name(self):
        return self._name

    @property
    def mode(self):
        """
        Returns the current correlator mode
        """
        self._init_lib()
        return self._parameters["mode"]

    @mode.setter
    def mode(self, mode):
        old_mode = self._parameters["mode"]
        if old_mode == mode:
            return

        try:
            acq_struct = Card.ENUM_2_ACQ[mode]
        except KeyError:
            raise KeyError("Mode could be %s" % [str(e) for e in self.MODE])

        if self._init:
            self._lib._USBFree()
            self._init = False

        if not self._lib._USBInitialize(acq_struct.init):
            raise RuntimeError(
                "Can not initialize correlator " " to mode **%s**" % str(mode)
            )
        self._init = True
        self._parameters["mode"] = mode

    def start_acquisition(self):
        """
        Start a continuous acquisition
        """
        if self._run_flag.value:
            return

        mode = self.mode
        acq_struct = Card.ENUM_2_ACQ[mode]
        self._lib._USBStart(acq_struct.start, 80, 0, 0)
        self._run_flag.value = True
        self._init_variables()
        self._read_task = gevent.spawn(self._flex_read, weakref.proxy(self))

    def stop_acquisition(self):
        """
        Stop the continuous acquisition
        """
        if not self._run_flag.value:
            return

        self._lib._USBStop()
        self._run_flag.value = False
        self._read_task.join()

    @property
    def intensities_and_acqtime(self):
        """
        return the mean intensity for canal A and B +
        the acquisition time.
        """
        if self._traceA:
            intensityA = float(sum(self._traceA)) / (len(self._traceA) * self.FLEX_TIME)
        else:
            intensityA = 0.
        if self._traceB:
            intensityB = float(sum(self._traceB)) / (len(self._traceB) * self.FLEX_TIME)
        else:
            intensityB = 0.
        acq_time = self._acq_time.value
        return (intensityA, intensityB, acq_time)

    @property
    def trace(self):
        """
        get the current traces
        """
        traces = numpy.zeros(
            len(self._traceA), dtype=[("time", "d"), ("traceA", "d"), ("traceB", "d")]
        )
        traces["time"] = numpy.arange(1, len(self._traceA) + 1) * self.FLEX_TIME
        traces["traceA"] = self._traceA
        traces["traceB"] = self._traceB
        return traces

    @property
    def data(self):
        """
        returns delay time, correlation functions
        """
        mode = self._parameters["mode"]
        if mode in (self.MODE.SINGLE_AUTO, self.MODE.SINGLE_CROSS):
            delay = self._calc_delay(64, 32, 32)
            raw_corr = self._rawcorr[: len(delay)]
            sample = self._sample[: len(delay)]
            base_a = self._baseA[: len(delay)]
            base_b = self._baseB[: len(delay)]
            base = base_a * base_b
            corr_data = raw_corr * sample
            corr_data[base != 0.] /= base[base != 0]
            corr_datas = [corr_data]
        elif mode in (self.MODE.DUAL_AUTO, self.MODE.DUAL_CROSS):
            delay = self._calc_delay(32, 36, 16)
            sample = self._sample[: len(delay)]
            raw_corr = self._rawcorr[: len(delay) * 2]
            raw_corr.shape = 2, -1
            base_a = self._baseA[: len(delay) * 2]
            base_a.shape = 2, -1
            base_b = self._baseB[: len(delay) * 2]
            base_b.shape = 2, -1
            base = base_a * base_b
            corr_data = raw_corr * sample
            corr_data[base != 0.] /= base[base != 0.]
            corr_datas = list(corr_data)
        else:  # QUAD
            delay = self._calc_delay(16, 34, 8)
            corr_datas = list()
            sample = self._sample[: len(delay)]
            for i in range(4):
                start_position = i * 304
                end_position = start_position + len(delay)
                raw_corr = self._rawcorr[start_position:end_position]
                base_a = self._baseA[start_position:end_position]
                base_b = self._baseB[start_position:end_position]
                base = base_a * base_b
                corr_data = raw_corr * sample
                corr_data[base != 0.] /= base[base != 0]
                corr_datas.append(corr_data)
        return [delay] + corr_datas

    @staticmethod
    def _calc_delay(linear_nb, nb_segment, nb_val_per_segment):
        flex_delay = Card.FLEX_DELAY
        delay = numpy.arange(1, linear_nb + 1, dtype=numpy.float) * flex_delay
        for i in range(nb_segment):
            flex_delay += flex_delay
            offset = delay[-1]
            sub_delay = (
                offset
                + numpy.arange(1, nb_val_per_segment + 1, dtype=numpy.float)
                * flex_delay
            )
            delay = numpy.append(delay, sub_delay)
        return delay

    @staticmethod
    def _flex_read(card_proxy):
        histoA = numpy.zeros(2048, dtype=numpy.double)
        histoB = numpy.zeros(2048, dtype=numpy.double)
        traceA = numpy.zeros(1024, dtype=numpy.double)
        traceB = numpy.zeros(1024, dtype=numpy.double)
        acq_time_p = ctypes.pointer(card_proxy._acq_time)
        trace_cnt = ctypes.c_uint16(0)
        trace_cnt_p = ctypes.pointer(trace_cnt)
        raw_corr_p = card_proxy._rawcorr.ctypes.data_as(ctypes.c_void_p)
        sample_p = card_proxy._sample.ctypes.data_as(ctypes.c_void_p)
        baseA_p = card_proxy._baseA.ctypes.data_as(ctypes.c_void_p)
        baseB_p = card_proxy._baseB.ctypes.data_as(ctypes.c_void_p)

        stop = False
        while True:
            card_proxy._lib._USBUpdateRawdata(
                acq_time_p,
                trace_cnt_p,
                raw_corr_p,
                sample_p,
                baseA_p,
                baseB_p,
                traceA.ctypes.data,
                traceB.ctypes.data,
                histoA.ctypes.data,
                histoB.ctypes.data,
            )
            nb_trace = trace_cnt.value
            card_proxy._traceA.extend(traceA[:nb_trace])
            card_proxy._traceB.extend(traceB[:nb_trace])
            gevent.idle()
            if stop:
                break
            elif not card_proxy._run_flag.value:
                stop = True
