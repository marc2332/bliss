# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.measurement import SamplingCounter
import random
import gevent

class simulation_diode_controller(object):
    @property
    def name(self):
        return 'simulation_diode_controller'

    def read_all(self, *counters):
        gevent.sleep(0.01)
        return [cnt.read(sleep=False) for cnt in counters]

CONTROLLER = simulation_diode_controller()

class simulation_diode(SamplingCounter):
    def __init__(self, name, config):
        if config.get("independent"):
            controller = None
        else:
            controller = CONTROLLER

        SamplingCounter.__init__(self, name, controller)

    def read(self, sleep=True):
        if sleep:
            gevent.sleep(0.01) # simulate hw reading
        return random.randint(-100,100)
