# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.measurement import CounterBase
import random
from gevent import sleep

class simulation_diode(CounterBase):
    def __init__(self, name, config):
        CounterBase.__init__(self, None, name)

    def read(self):
        sleep(0.01) # simulate hw reading
        return random.randint(-100,100)
