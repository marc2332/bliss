# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.tango_attr_as_counter import TangoAttrCounter


class tango_fe(TangoAttrCounter):
    def __init__(self, name, config):
        TangoAttrCounter.__init__(self, name, config)
