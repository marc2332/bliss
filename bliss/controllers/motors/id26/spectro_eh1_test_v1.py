# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss controller for  5-motors spectrometer test bench in EH1
(ID26)

"""
# IMPORTS #
from bliss.controllers.motor import CalcController
from bliss.common import log as elog

import math

# GLOBAL VARIABLES #
HC = 1.2398418743309972e-06  # eV * m
ALAT_SI = 5.431065  # Ang at 25C
ALAT_GE = 5.6579060  # Ang at 25C

# USER SETTINGS #
CRYST_MAT = "Si"  # or 'Ge' : analyser crystal material
CRYST_HKL = [4, 4, 4]  # analyser crystal reflection [h,k,l]
CRYST_ALPHA = 0.0  # miscut angle in degrees
CRYST_R = 1000.  # analyser bending radius in mm (=2*Rm)


# UTILITY FUNCTIONS #
def kev2wlen(energy):
    """ convert photon energy (E, keV) to wavelength ($\lambda$, \AA$^{-1}$)"""
    return (HC / energy) * 1e7


def wlen2kev(wlen):
    """ convert photon wavelength ($\lambda$, \AA$^{-1}$) to energy (E, keV)"""
    return (HC / wlen) * 1e7


def sqrt1over(d2m):
    if d2m == 0:
        return 0
    else:
        return math.sqrt(1 / d2m)


def d_cubic(a, hkl):
    """d-spacing for a cubic lattice"""
    h, k, l = hkl[0], hkl[1], hkl[2]
    d2m = (h ** 2 + k ** 2 + l ** 2) / a ** 2
    return sqrt1over(d2m)


def theta_b(ene, d):
    """Bragg angle (rad) given energy (keV) and d-spacing (\AA)"""
    if not (d == 0):
        return math.asin((kev2wlen(ene)) / (2 * d))
    else:
        print("ERROR: d-spacing is 0")
        return


def bragg_kev(theta, d):
    """energy (keV) given Bragg angle (deg) and d-spacing (\AA)"""
    return wlen2kev(2 * d * math.sin(math.radians(theta)))


def get_dspacing(mat, hkl):
    """get d-spacing for given crystal material and reflection (hkl)"""
    if mat == "Si":
        dspacing = d_cubic(ALAT_SI, hkl)
    elif mat == "Ge":
        dspacing = d_cubic(ALAT_GE, hkl)
    else:
        print("ERROR: available materials -> 'Si' 'Ge'")
        dspacing = 0
    return dspacing


# CALC FUNCTIONS #
# these functions could be inside the class, but I prefer to keep them
# outside to run/check in IPython
def ene2mots(energy, mat=None, hkl=None, r=None, alpha=None, pp=False):
    """calculates the real positions of the motors for a given energy (kev)

    Returns a list with positions: [atheh1, axeh1, dtheh1, dxeh1, dyeh1]
    """
    if mat is None:
        mat = CRYST_MAT
    if hkl is None:
        hkl = CRYST_HKL
    if r is None:
        r = CRYST_R
    if alpha is None:
        alpha = CRYST_ALPHA
    rthetab = theta_b(energy, get_dspacing(mat, hkl))
    ralpha = math.radians(alpha)
    p0 = r * math.sin(rthetab + ralpha)
    q0 = r * math.sin(rthetab - ralpha)

    atheh1 = math.degrees(rthetab)
    axeh1 = p0
    dtheh1 = 2 * math.degrees(rthetab)
    dxeh1 = p0 + q0 * math.cos(2 * rthetab)
    dyeh1 = q0 * math.sin(2 * rthetab)

    _mot_list = [atheh1, axeh1, dtheh1, dxeh1, dyeh1]

    if pp:
        # pretty print (= for humans)
        _tmpl_head = "MOT: {0:=^10} {1:=^10} {2:=^10} {3:=^10} {4:=^10}"
        _tmpl_data = "POS: {0:^ 10.4f} {1:^ 10.4f} {2:^ 10.4f} {3:^ 10.4f} {4:^ 10.4f}"
        print((_tmpl_head.format("ath", "ax", "dth", "dx", "dy")))
        print((_tmpl_data.format(*_mot_list)))
    else:
        return _mot_list


def mots2steps(mot_list, conv_list=None, pp=True):
    """converts the motors real positions to steps using a conversion list"""

    if conv_list is None:
        #           [atheh1, axeh1, dtheh1, dxeh1, dyeh1]
        conv_list = [5000.0, 4000.0, 1000.0, 2000.0, 2000.0]

    _step_list = list()

    for m, s in zip(mot_list, conv_list):
        _step_list.append(m * s)

    if pp:
        # pretty print (=for humans)
        _tmpl_head = "MOT: {0:=^10} {1:=^10} {2:=^10} {3:=^10} {4:=^10}"
        _tmpl_data = "POS: {0:^ 10.4f} {1:^ 10.4f} {2:^ 10.4f} {3:^ 10.4f} {4:^ 10.4f}"
        _tmpl_step = "STP: {0:^ 10.0f} {1:^ 10.0f} {2:^ 10.0f} {3:^ 10.0f} {4:^ 10.0f}"
        print((_tmpl_head.format("ath", "ax", "dth", "dx", "dy")))
        print((_tmpl_data.format(*mot_list)))
        print((_tmpl_step.format(*_step_list)))
    else:
        return _step_list


# CLASS #
class spectro_eh1_test_V1(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)

        # get CRYST_R from config file.
        # self.CRYST_R = self.config.get("CRYST_R", float)
        # or use global variable

    #     def initialize_axis(self, axis):
    #         CalcController.initialize_axis(self, axis)
    #         print "initialize_axis"

    def set_CRYST_R(self, axis, new_radius):
        self.CRYST_R = float(new_radius)
        return self.CRYST_R

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
