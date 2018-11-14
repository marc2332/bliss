#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
# Distributed under the GNU LGPLv3. See LICENSE.txt for more info.

# Simple python script to test bliss and beacon
#
# needs a ". blissrc"

from bliss.config import static

cfg = static.get_config()
ra = cfg.get("ra")
print("ra velocity : %g" % ra.velocity())
