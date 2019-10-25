# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.cleanup import cleanup, error_cleanup
from bliss.common.task import task
from bliss.common.counter import SamplingCounter
from bliss.common import AbstractActuator as Actuator
from bliss.comm.Exporter import *
import time
import numpy


class md3photodiode(SamplingCounter, Actuator):
    def __init__(self, name, config):
        SamplingCounter.__init__(self, name, None)
        Actuator.__init__(self)

        self.host, self.port = config.get("exporter_address").split(":")
        self._exporter = None

    def _ready(self):
        if self._exporter is None:
            self._exporter = Exporter(self.host, int(self.port))

        if (
            self._exporter.readProperty("State") == "Ready"
            and self._exporter.readProperty("HardwareState") == "Ready"
        ):
            return True

        return False

    def _set_in(self):
        if self._ready():
            self._exporter.writeProperty("ScintillatorPosition", "PHOTODIODE")

    def _set_out(self):
        if self._ready():
            self._exporter.writeProperty("ScintillatorPosition", "PARK")
        return False

    def _is_in(self):
        if self._ready():
            return self._exporter.readProperty("ScintillatorPosition") == "PHOTODIODE"
        return False

    def _is_out(self):
        if self._ready():
            return self._exporter.readProperty("ScintillatorPosition") == "PARK"
        return False

    def read(self):
        if self._ready():
            return self._exporter.execute("readPhotodiodeSignal", 0)
        return None
