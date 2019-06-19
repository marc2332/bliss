"""
Bliss controller for  6-motors spectrometer test bench in EH1
(ID26)

TEST BENCH VERSION 2 (2015/05)

*NOTE*: the test bench version 2 is NOT a revised version of the test
bench v1, but really another geometry!!! In this version the
sample-detector are on the same axis.

Author: Mauro Rovezzi (mauro.rovezzi@esrf.eu)

<!-- REAL MOTORS -->
<axis name="athe1" tags="real m1" />
<axis name="axe1" tags="real  m2" />
<axis name="dthe1" tags="real m3" />
<axis name="dxe1" tags="real  m4" />
<axis name="dye1" tags="real  m5" />
<axis name="aye1" tags="real  m6" />
<axis name="sze1" tags="real  m7" />
<!-- CALCULATED MOTORS -->
<axis name="xen1" tags="xes_en_eh1">
<axis name="xythe1" tags="xy_theta_eh1">

"""
# IMPORTS #
from bliss.controllers.motor import CalcController
import math

from bliss.physics import spectroscopy

# GLOBAL VARIABLES #
ALAT_SI = 5.431065  # Ang at 25C
ALAT_GE = 5.6579060  # Ang at 25C

# USER SETTINGS #
CRYST_MAT = "Si"  # or 'Ge' : analyser crystal material
CRYST_HKL = [4, 4, 4]  # analyser crystal reflection [h,k,l]
CRYST_ALPHA = 0.0  # miscut angle in degrees
CRYST_R = 1000.  # analyser bending radius in mm (=2*Rm)


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
    """Bragg angle (rad) given energy (keV) and d-spacing (angstroms)"""
    if not (d == 0):
        return math.asin(
            (spectroscopy.energy_kev_to_wavelength_angstrom(ene)) / (2 * d)
        )
    else:
        print("ERROR: d-spacing is 0")
        return


def bragg_kev(theta, d):
    """energy (keV) given Bragg angle (deg) and d-spacing (angstroms)"""
    return spectroscopy.wavelength_angstrom_to_energy_kev(
        2 * d * math.sin(math.radians(theta))
    )


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


CRYST_D = get_dspacing(CRYST_MAT, CRYST_HKL)


def get_xyth(ax, ay):
    """theta from xy"""
    if ax == 0:
        return 0.0001
    else:
        return math.degrees(math.atan(ax / ay))


# CALC FUNCTIONS #
# these functions could be inside the class, but I prefer to keep them
# outside to run/check in IPython
def ene2mots(energy, mat=None, hkl=None, r=None, alpha=None, pp=False):
    """calculates the real positions of the motors for a given energy (kev)

    Returns a list with positions: [axe1, aye1, dthe1, dye1]
    """
    if mat is None:
        mat = CRYST_MAT
    if hkl is None:
        hkl = CRYST_HKL
    if r is None:
        r = CRYST_R
    if alpha is None:
        alpha = CRYST_ALPHA

    # angles
    rthetab = theta_b(energy, get_dspacing(mat, hkl))
    ralpha = math.radians(alpha)
    # distances
    p0 = r * math.sin(rthetab - ralpha / 2.)
    q0 = r * math.sin(rthetab + ralpha / 2.)
    # analyzer positions
    axe1 = p0 * math.sin(rthetab)
    aye1 = p0 * math.cos(rthetab)
    # detector positions
    dthe1 = math.degrees(rthetab)
    dye1 = 2 * r * math.sin(rthetab) * math.cos(rthetab)  # NO MISCUT!!!

    _mot_list = [axe1, aye1, dthe1, dye1]

    if pp:
        # pretty print (= for humans)
        _tmpl_head = "MOT: {0:=^10} {1:=^10} {2:=^10} {3:=^10}"
        _tmpl_data = "POS: {0:^ 10.4f} {1:^ 10.4f} {2:^ 10.4f} {3:^ 10.4f}"
        print((_tmpl_head.format("ax", "ay", "dth", "dy")))
        print((_tmpl_data.format(*_mot_list)))
    else:
        return _mot_list


def th2xy(xyth, r=None):
    """calc xy given theta"""
    if r is None:
        r = CRYST_R
    rth = math.radians(xyth)
    ax = r * math.sin(rth) * math.sin(rth)
    ay = r * math.sin(rth) * math.cos(rth)
    return [ax, ay]


def mots2steps(mot_list, conv_list=None, pp=True):
    """converts the motors real positions to steps using a conversion list"""

    if conv_list is None:
        #           [ axe1,     aye1,     dthe1,   dye1]
        conv_list = [-10000.0, -10000.0, -1000.0, -2000.0]

    _step_list = list()

    for m, s in zip(mot_list, conv_list):
        _step_list.append(m * s)

    if pp:
        # pretty print (=for humans)
        _tmpl_head = "MOT: {0:=^10} {1:=^10} {2:=^10} {3:=^10}"
        _tmpl_data = "POS: {0:^ 10.4f} {1:^ 10.4f} {2:^ 10.4f} {3:^ 10.4f}"
        _tmpl_step = "STP: {0:^ 10.0f} {1:^ 10.0f} {2:^ 10.0f} {3:^ 10.0f}"
        print((_tmpl_head.format("ax", "ay", "dth", "dy")))
        print((_tmpl_data.format(*mot_list)))
        print((_tmpl_step.format(*_step_list)))
    else:
        return _step_list


# CLASS #
class spectro_eh1_test_V2(CalcController):
    def __init__(self, *args, **kwargs):
        CalcController.__init__(self, *args, **kwargs)
        self._pos_dict = {}

        # get CRYST_R from config file.
        # self.CRYST_R = self.config.get("CRYST_R", float)
        # or use global variable

    def initialize_axis(self, axis):
        CalcController.initialize_axis(self, axis)

    def set_CRYST_R(self, axis, new_radius):
        self.CRYST_R = float(new_radius)
        return self.CRYST_R

    def calc_from_real(self, positions_dict):
        """return virtual motors positions dictionary given real
        (INFO: method called when a real motor is moved)
        """
        self._pos_dict = positions_dict  # used to store ALL motors positions
        axe1 = positions_dict["m2"]
        aye1 = positions_dict["m6"]
        xythetab = get_xyth(axe1, aye1)
        xes_en_eh1 = bragg_kev(xythetab, get_dspacing(CRYST_MAT, CRYST_HKL))
        _virt_dict = {"xes_en_eh1": xes_en_eh1, "xy_theta_eh1": xythetab}
        self._pos_dict.update(_virt_dict)
        return _virt_dict

    def calc_to_real(self, positions_dict):
        """return real motors positions dictionary given virtual
        (INFO: method called when a virtual motor is moved)
        """
        xes_en_eh1 = positions_dict["xes_en_eh1"]
        xy_theta_eh1 = positions_dict["xy_theta_eh1"]
        if xes_en_eh1 == self._pos_dict["xes_en_eh1"]:
            # xythe1 is scanned
            _varmot_list = th2xy(positions_dict["xy_theta_eh1"])
            _real_dict = {
                "m1": self._pos_dict["m1"],
                "m2": _varmot_list[0],
                "m3": self._pos_dict["m3"],
                "m4": self._pos_dict["m4"],
                "m5": self._pos_dict["m5"],
                "m6": _varmot_list[1],
                "m7": self._pos_dict["m7"],
            }
            return _real_dict

        _varmot_list = ene2mots(xes_en_eh1, pp=False)  # only variable motors
        # _varmot_list :: [axe1, aye1, dthe1, dye1]
        #                 0     1     2      3
        #                 m2    m6    m3     m5
        _real_dict = {
            "m1": self._pos_dict["m1"],
            "m2": _varmot_list[0],
            "m3": _varmot_list[2],
            "m4": self._pos_dict["m4"],
            "m5": _varmot_list[3],
            "m6": _varmot_list[1],
            "m7": self._pos_dict["m7"],
        }
        return _real_dict


# FOR TESTS #
if __name__ == "__main__":
    pass
