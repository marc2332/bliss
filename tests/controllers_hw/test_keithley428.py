# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import time
from bliss.controllers.keithley428 import keithley428

config = {
    "gpib_url": "prologix://148.79.215.54:1234",
    "gpib_pad": 22,
    "gpib_timeout": 5.0,
    "gpib_eos": "\r\n",
}
dev = keithley428("keithley", config)
print(dev.State)
print(dev.FilterRiseTime)
try:
    for rt in range(11):
        dev.FilterRiseTime = rt
        print(dev.FilterRiseTime)
except Exception as e:
    print(e)
try:
    for gn in range(12):
        dev.Gain = gn
        print(dev.Gain)
except Exception as e:
    print(e)

dev.ZeroCheckOff
dev.VoltageBiasOn
dev.CurrentSuppressOff
print(dev.VoltageBias)
dev.VoltageBias = 0.01
print(dev.VoltageBias)
dev.VoltageBias = 0.05
print(dev.VoltageBias)

print("state ", dev.State)
print("Overloaded? ", dev.Overloaded)
print("Filter state ", dev.FilterState)
dev.FilterOn
print("Filter state ", dev.FilterState)
dev.FilterOff
print("Filter state ", dev.FilterState)

print("Auto Filter state ", dev.AutoFilterState)
dev.AutoFilterOff
print("Auto Filter state ", dev.AutoFilterState)
dev.AutoFilterOn
print("Auto Filter state ", dev.AutoFilterState)

dev.CurrentSuppressOn
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.0006
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.00007
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.000008
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.0000009
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.00000006
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.000000007
print(dev.CurrentSuppress)
dev.CurrentSuppress = 0.0000000008
print(dev.CurrentSuppress)
try:
    dev.CurrentSuppress = 0.00000000009
except Exception as e:
    print(e)
dev.CurrentSuppressOff
