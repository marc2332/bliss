# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss.common.measurement import SamplingCounter, IntegratingCounter


class Diode(SamplingCounter):
    def __init__(self, diode, convert_func):
        SamplingCounter.__init__(
            self,
            "test_diode",
            None,
            grouped_read_handler=None,
            conversion_function=convert_func,
        )
        self.diode = diode

    def read(self, *args):
        self.last_read_value = self.diode.read()
        return self.last_read_value


class DiodeWithController(SamplingCounter):
    def __init__(self, diode, convert_func):
        SamplingCounter.__init__(
            self,
            "test_diode",
            diode.controller,
            grouped_read_handler=None,
            conversion_function=convert_func,
        )
        self.diode = diode


class AcquisitionController:
    pass


class IntegCounter(IntegratingCounter):
    def __init__(self, acq_controller, convert_func):
        IntegratingCounter.__init__(
            self,
            "test_integ_diode",
            None,
            acq_controller,
            grouped_read_handler=None,
            conversion_function=convert_func,
        )

    def get_values(self, from_index):
        return numpy.random.random(20)


def test_diode(beacon):
    diode = beacon.get("diode")

    def multiply_by_two(x):
        return 2 * x

    test_diode = Diode(diode, multiply_by_two)

    diode_value = test_diode.read()

    assert test_diode.last_read_value * 2 == diode_value


def test_diode_with_controller(beacon):
    diode = beacon.get("diode")

    def multiply_by_two(x):
        diode.raw_value = x
        return 2 * x

    test_diode = Diode(diode, multiply_by_two)

    diode_value = test_diode.read()

    assert diode.raw_value * 2 == diode_value


def test_integ_counter(beacon):
    acq_controller = AcquisitionController()

    def multiply_by_two(x):
        acq_controller.raw_value = x
        return 2 * x

    counter = IntegCounter(acq_controller, multiply_by_two)

    assert list(counter.get_values(0)) == list(2 * acq_controller.raw_value)
