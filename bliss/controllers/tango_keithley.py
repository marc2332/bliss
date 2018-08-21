# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.measurement import SamplingCounter
from bliss.common.tango import DeviceProxy
import time
import numpy


class tango_keithley(SamplingCounter):
    def __init__(self, name, config):
        SamplingCounter.__init__(self, name, None)
        tango_uri = config["uri"]
        self.__control = DeviceProxy(tango_uri)

    def read(self):
        self.__control.MeasureSingle()
        self.__control.WaitAcq()
        value = self.__control.ReadData
        if isinstance(value, numpy.ndarray):
            value = value[0]
        return value

    def autorange(self, autorange_on=None):
        if autorange_on is None:
            return self.__control.autorange
        else:
            self.__control.autorange = autorange_on

    @property
    def range(self):
        return self.__control.range

    @range.setter
    def range(self, range):
        self.__control.range = range

    def autozero(self, autozero_on=None):
        if autozero_on is None:
            return self.__control.autozero
        else:
            self.__control.autozero = autozero_on

    def init(self):
        return self.__control.init()
