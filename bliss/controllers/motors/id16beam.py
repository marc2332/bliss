# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss Calculational controller to folllow beam trajectory
real motors : Sx Sy Sz
Calc motors : Bx By Bz
ID16A (ni)

"""
# IMPORTS #
from bliss.controllers.motor import CalcController
from bliss.common import log as elog


import math


class id16beam(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        # get theta_y theta_z from config file.
        self.theta_y = self.config.get("theta_y", float)
        self.theta_z = self.config.get("theta_z", float)

    #     def initialize_axis(self, axis):
    #         CalcController.initialize_axis(self, axis)
    #         print "initialize_axis"
    #

    def calc_from_real(self, positions_dict):
        """calculates the energy pseudo from the real position of atheh1"""
        thetab = positions_dict["m1"]
        if thetab == 0:
            thetab = 0.0001
        xes_en_eh1 = bragg_kev(thetab, get_dspacing(CRYST_MAT, CRYST_HKL))
        _virt_dict = {"xes_en_eh1": xes_en_eh1}
        return _virt_dict

    def calc_to_real(self, positions_dict):
        """returns real motors positions (as a dictionary) given virtual"""
        xes_en_eh1 = positions_dict["xes_en_eh1"]
        _mot_list = ene2mots(xes_en_eh1, pp=False)
        _real_dict = {
            "m1": _mot_list[0],
            "m2": _mot_list[1],
            "m3": _mot_list[2],
            "m4": _mot_list[3],
            "m5": _mot_list[4],
        }

        return _real_dict


# FOR TESTS #
if __name__ == "__main__":
    pass
