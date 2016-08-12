# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

import bliss
from bliss.common.axis import Axis

import bliss
import bliss.controllers.motor_settings
from bliss.common.axis import Axis
from bliss.common import event
from bliss.common import log
from bliss.config.motors import set_backend
from bliss.config import settings


set_backend("beacon")
bliss.config.motors.clear_cfg()
bliss.controllers.motor_settings.wait_settings_writing()


print ""

ba1 = bliss.get_axis("ba1")

print ba1.get_cust_attr_float()

#ba1.dial()
#print ba1.get_cust_attr_float()

print ""
