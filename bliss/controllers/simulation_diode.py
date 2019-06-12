# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import random
import gevent

from bliss.common.measurement import SamplingCounter, IntegratingCounter

"""
example of configuration:
-
  name: simulated_diode1
  plugin: bliss
  class: simulation_diode
  independent: True
-
  name: simulated_diode2
  plugin: bliss
  class: simulation_diode
-
  name: simulated_diode3
  plugin: bliss
  class: simulation_diode
  integration: True
"""


class simulation_diode_controller(object):
    @property
    def name(self):
        return "simulation_diode_controller"

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


class CstSimulationDiodeSamplingCounter(SamplingCounter):
    def __init__(self, *args, **kwargs):
        super(CstSimulationDiodeSamplingCounter, self).__init__(*args, **kwargs)
        self.cst_val = 0

    def set_cst_value(self, value):
        self.cst_val = value

    def read(self, sleep=True):
        if sleep:
            gevent.sleep(0.01)  # simulate hw reading
        return self.cst_val


class SimulationDiodeIntegratingCounter(IntegratingCounter):
    def get_values(self, from_index, sleep=True):
        if sleep:
            gevent.sleep(0.01)
        return 10 * [random.randint(-100, 100)]


DEFAULT_CONTROLLER = simulation_diode_controller()


def simulation_diode(name, config, default=DEFAULT_CONTROLLER):
    controller = None if config.get("independent") else default
    if config.get("integration"):
        return SimulationDiodeIntegratingCounter(name, controller, lambda: None)
    if config.get("constant") is not None:
        diode = CstSimulationDiodeSamplingCounter(name, controller)
        diode.set_cst_value(int(config.get("constant")))
        return diode
    return SimulationDiodeSamplingCounter(name, controller)
