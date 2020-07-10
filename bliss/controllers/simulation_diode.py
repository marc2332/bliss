# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import random
import gevent

from bliss.common.counter import SamplingCounter, IntegratingCounter

from bliss.controllers.counter import (
    SamplingCounterController,
    IntegratingCounterController,
)

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


class SimulationDiodeController(SamplingCounterController):
    _read_overhead = 0.01

    def __init__(self):
        super().__init__(name="simulation_diode_sampling_controller")

    def read_all(self, *counters):
        gevent.sleep(self._read_overhead)
        return [
            cnt.cst_val
            if isinstance(cnt, CstSimulationDiodeSamplingCounter)
            else random.randint(1, 10000) / 100.0
            for cnt in counters
        ]


class SimulationDiodeIntegrationController(IntegratingCounterController):
    _read_overhead = 0.01

    def __init__(self):
        super().__init__(name="simulation_diode_integrating_controller")

    def get_values(self, from_index, *counters):
        gevent.sleep(self._read_overhead)
        return [10 * [random.randint(1, 10000) / 100.0] for cnt in counters]


class SimulationDiodeSamplingCounter(SamplingCounter):
    pass


class CstSimulationDiodeSamplingCounter(SamplingCounter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cst_val = 0

    def set_cst_value(self, value):
        self.cst_val = value


class SimulationDiodeIntegratingCounter(IntegratingCounter):
    pass


DEFAULT_CONTROLLER = None
DEFAULT_INTEGRATING_CONTROLLER = None


def simulation_diode(name, config):
    if config.get("independent"):
        # assuming independent sampling counter controller
        controller = SimulationDiodeController()
    else:
        global DEFAULT_CONTROLLER
        global DEFAULT_INTEGRATING_CONTROLLER
        if config.get("integration"):
            if DEFAULT_INTEGRATING_CONTROLLER is None:
                DEFAULT_INTEGRATING_CONTROLLER = SimulationDiodeIntegrationController()
            return SimulationDiodeIntegratingCounter(
                name, DEFAULT_INTEGRATING_CONTROLLER
            )
        else:
            if DEFAULT_CONTROLLER is None:
                DEFAULT_CONTROLLER = SimulationDiodeController()
            controller = DEFAULT_CONTROLLER
    if config.get("constant") is not None:
        diode = CstSimulationDiodeSamplingCounter(name, controller)
        diode.set_cst_value(int(config.get("constant")))
    elif config.get("mode") is not None:
        diode = SimulationDiodeSamplingCounter(
            name, controller, mode=config.get("mode")
        )
    else:
        diode = SimulationDiodeSamplingCounter(name, controller)
    return diode
