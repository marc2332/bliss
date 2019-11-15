# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.counter import CalcCounterController


# Mean calculation
class MeanCalcCounterController(CalcCounterController):
    def calc_function(self, input_dict):

        csum = 0
        for cnt in self.inputs:
            csum += input_dict[self.tags[cnt.name]]

        csum = csum / float(len(self.inputs))

        return {self.tags[self.outputs[0].name]: csum}
