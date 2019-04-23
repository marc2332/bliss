# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import random

import gevent

from bliss.comm.scpi import Commands
from bliss.controllers.keithley_scpi_mapping import COMMANDS, MODEL_COMMANDS

from .scpi import SCPI

# 'KEITHLEY INSTRUMENTS INC.,MODEL 6485,1008577,B03   Sep 25 2002 10:53:29/A02  /E'


class BaseKeithley(SCPI):

    Manufacturer = "KEITHLEY INSTRUMENTS INC."
    Version = "1008577"
    Firmware = "B03   Sep 25 2002 10:53:29/A02  /E"
    IDNFieldSep = ","

    def __init__(self, *args, **kwargs):
        super(BaseKeithley, self).__init__(*args, **kwargs)
        self.start_time = time.time()

    def syst_ver(self):
        return self.Version


class Keithley6485(BaseKeithley):

    Model = "MODEL 6485"

    PLC = 50  # 50Hz
    NPLC = 5.0
    FormElem = ("READ",)

    def __init__(self, *args, **kwargs):
        kwargs["commands"] = Commands(COMMANDS, MODEL_COMMANDS["6485"])
        super(Keithley6485, self).__init__(*args, **kwargs)

    #    def curr_nplc(self, is_query, value=None):
    #        if is_query:
    #            return self.NPLC
    #        self.NPLC = float(value)

    def curr_rang(self):
        return 123.456

    def form_elem(self, is_query, value=None):
        if is_query:
            return ",".join(self.FormElem)
        self.FormElem = tuple(map(str.upper, value.split(",")))

    def read(self):
        # assumptions: reading from sensor and result in SCI notation
        # emulate read time
        gevent.sleep(self.NPLC * 1. / self.PLC)
        result = []
        for i in self.FormElem:
            if i == "READ":
                result.append("%EA" % (random.random() * (20E-3 - 2E-9) + 2E-9))
            elif i == "TIME":
                ts = (time.time() - self.start_time) % 99999.99
                result.append("%E" % ts)
        return ",".join(result)

    def meas(self):
        return self.read()
