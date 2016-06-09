# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.measurement import CounterBase, AverageMeasurement
import random
from time import sleep

class simulation_diode(CounterBase):
    def __init__(self, name, config):
        CounterBase.__init__(self, name)

    def count(self, time=None, measurement=None):
        meas = measurement or self.Measurement()
        for reading in meas(time):
            if time > 0.01:
                sleep(0.01) # simulate hw reading
            reading.value = random.randint(-100,100)
        return meas
