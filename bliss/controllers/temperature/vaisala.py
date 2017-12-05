# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.comm.util import get_comm
from bliss.controllers import vaisala
from bliss.controllers.temp import Controller
from bliss.common.temperature import Input, Output, Loop


class HMT330(Controller):

    def initialize(self):

        config = dict(self.config)
        config['counters'] = counters = []
        for inp_cfg in self.config.get('inputs', ()):
            inp_cfg['counter name'] = inp_cfg['name']
            counters.append(inp_cfg)
        name = config.setdefault('name', 'hmt330')
        self.dev = vaisala.HMT330(name, config)

    def read_input(self, tinput):
        channel = tinput.config['channel']
        return self.dev[channel]
