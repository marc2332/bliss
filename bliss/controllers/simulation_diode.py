# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.measurement import SamplingCounter
import random
from gevent import sleep

class simulation_diode(SamplingCounter):
    def __init__(self, name, config):
        SamplingCounter.__init__(self, name, None)

    def read(self):
        sleep(0.01) # simulate hw reading
        return random.randint(-100,100)
