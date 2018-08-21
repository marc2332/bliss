# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import Actuator


class detector_cover(Actuator):
    def __init__(self, name, config):
        Actuator.__init__(self)

        self.wago = config["controller"]
        self.key_in = config["cover_state_in"]
        self.key_out = config["cover_state_out"]
        self.key_cmd = config["cover_cmd"]

    def _set_in(self):
        self.wago.set(self.key_cmd, 0)

    def _set_out(self):
        self.wago.set(self.key_cmd, 1)

    def _is_in(self):
        return self.wago.get(self.key_in)

    def _is_out(self):
        return self.wago.get(self.key_out)
