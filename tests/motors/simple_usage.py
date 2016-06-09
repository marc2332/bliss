# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys

import bliss

xml_config = """
<config>
  <controller class="mockup">
    <axis name="axis0">
    <velocity value="100"/>
    <acceleration value="1"/>
    </axis>
  </controller>
</config>
"""

bliss.load_cfg_fromstring(xml_config)
my_axis = bliss.get_axis("axis0")

print my_axis.position()
my_axis.move(42)
print my_axis.position()

