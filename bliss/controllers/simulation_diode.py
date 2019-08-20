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


class DummySimulationDiodeController:
    @property
    def name(self):
        return "simulation_diode_controller"


class SimulationDiodeController(DummySimulationDiodeController):
    def read_all(self, *counters):
        gevent.sleep(0.01)
        return [random.randint(-100, 100) for cnt in counters]


class SimulationIntegrationDiodeController(DummySimulationDiodeController):
    def get_values(self, from_index, *counters):
        gevent.sleep(0.01)
        return [10 * [random.randint(-100, 100)] for cnt in counters]


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


DEFAULT_CONTROLLER = SimulationDiodeController()
DEFAULT_INTEGRATING_CONTROLLER = SimulationIntegrationDiodeController()


def simulation_diode(name, config):
    if config.get("independent"):
        # assuming independent sampling counter controller
        controller = DummySimulationDiodeController()
    else:
        if config.get("integration"):
            return SimulationDiodeIntegratingCounter(
                name, DEFAULT_INTEGRATING_CONTROLLER, None
            )
        else:
            controller = DEFAULT_CONTROLLER
    if config.get("constant") is not None:
        diode = CstSimulationDiodeSamplingCounter(name, controller)
        diode.set_cst_value(int(config.get("constant")))
        return diode
    if config.get("mode") is not None:
        return SimulationDiodeSamplingCounter(name, controller, mode=config.get("mode"))
    return SimulationDiodeSamplingCounter(name, controller)
