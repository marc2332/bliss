# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.measurement import SamplingCounter, IntegratingCounter
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
import random
import gevent

class simulation_diode_controller(object):
    @property
    def name(self):
        return 'simulation_diode_controller'

    def read_all(self, *counters):
        gevent.sleep(0.01)
        return [cnt.read(sleep=False) for cnt in counters]

    ### INTEGRATING COUNTER ###
    def create_master_device(self, scan_pars, **settings):
        return SoftwareTimerMaster(scan_pars['count_time'])

    def get_values(self, from_index, *counters):
        gevent.sleep(0.01)
        return [cnt.get_values(from_index,sleep=False) for cnt in counters]

CONTROLLER = simulation_diode_controller()

class simulation_diode(SamplingCounter):
    def __init__(self, name, config):
        if config.get("independent"):
            controller = None
        else:
            controller = CONTROLLER
        if config.get("integration"):
            self.__class__ = integ_simulation_diode
            IntegratingCounter.__init__(self, name, controller, controller)
        else:
            SamplingCounter.__init__(self, name, controller)

    def read(self, sleep=True):
        if sleep:
            gevent.sleep(0.01) # simulate hw reading
        return random.randint(-100,100)

class integ_simulation_diode(IntegratingCounter):
    def get_values(self, from_index, sleep=True):
        if sleep:
            gevent.sleep(0.01)
        return 10*[random.randint(-100,100)]
