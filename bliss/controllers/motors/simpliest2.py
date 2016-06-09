# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import CalcController


class simpliest2(CalcController):

    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

    def calc_from_real(self, positions_dict):
        return {"mB": positions_dict["mA"] * 2}

    def calc_to_real(self, positions_dict):
        return {"mA": positions_dict["mB"] / 2}
