# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.counter import CalcCounter
from bliss.controllers.counter import CalcCounterController

# Mean calculation
class MeanCalcCounterController(CalcCounterController):
    def get_counters(self, config):

        # Config reading
        for cnt in config["inputs"]:
            self.tags[cnt.name] = cnt.name
            self.inputs.append(cnt)

        for cnt_name in config["outputs"]:
            cnt = CalcCounter(cnt_name, self)
            self.outputs.append(cnt)
            self.tags[cnt.name] = cnt_name

    def calc_function(self, input_dict):

        csum = 0
        for cnt in self.inputs:

            csum += input_dict[cnt.name]

        csum = csum / float(len(self.inputs))

        return {self.outputs[0].name: csum}
