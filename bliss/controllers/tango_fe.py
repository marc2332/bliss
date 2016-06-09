# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.measurement import CounterBase, SingleMeasurement
import PyTango.gevent
import time

class tango_fe(CounterBase):

    Measurement = SingleMeasurement

    def __init__(self, name, config):
        CounterBase.__init__(self, name)
        tango_uri = config.get("uri")
        self.__control = PyTango.gevent.DeviceProxy(tango_uri)
        self.attribute = config.get("attr_name")

    def read(self):
        try:
            return self.__control.read_attribute(self.attribute).value
        except:
            return 0
