# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import random

import gevent

from bliss.common.measurement import SamplingCounter, IntegratingCounter


class simulation_diode_controller(object):
    @property
    def name(self):
        return 'simulation_diode_controller'

    def read_all(self, *counters):
        gevent.sleep(0.01)
        return [cnt.read(sleep=False) for cnt in counters]

    def get_values(self, from_index, *counters):
        gevent.sleep(0.01)
        return [cnt.get_values(from_index, sleep=False) for cnt in counters]


class SimulationDiodeSamplingCounter(SamplingCounter):

    def read(self, sleep=True):
        if sleep:
            gevent.sleep(0.01)  # simulate hw reading
        return random.randint(-100, 100)


class SimulationDiodeIntegratingCounter(IntegratingCounter):
    def get_values(self, from_index, sleep=True):
        if sleep:
            gevent.sleep(0.01)
        return 10 * [random.randint(-100, 100)]


DEFAULT_CONTROLLER = simulation_diode_controller()


def simulation_diode(name, config, default=DEFAULT_CONTROLLER):
    controller = None if config.get("independent") else default
    if config.get("integration"):
        return SimulationDiodeIntegratingCounter(name, controller)
    return SimulationDiodeSamplingCounter(name, controller)
