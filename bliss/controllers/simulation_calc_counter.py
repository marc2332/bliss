# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.counter import CalcCounterController

"""
config example:

- plugin: bliss
  module: simulation_calc_counter
  class: MeanCalcCounterController
  name: simul_calc_controller
  inputs:
    - counter: $diode
      tags: data1

    - counter: $diode2
      tags: data2

  outputs:
    - name: out1
"""


# Mean calculation
class MeanCalcCounterController(CalcCounterController):
    """
    This calculation counter takes a variable number of inputs and computes
    the average of all of them.
    """

    def calc_function(self, input_dict):
        csum = 0
        for cnt in self.inputs:
            csum += input_dict[self.tags[cnt.name]]

        csum = csum / float(len(self.inputs))

        return {self.tags[self.outputs[0].name]: csum}
