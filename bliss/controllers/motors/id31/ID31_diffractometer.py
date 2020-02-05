# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from numpy import power, sqrt, pi, roots, float64
from numpy import sin, arcsin, cos, tan, arctan, rad2deg, deg2rad


class Constant:
    h = 6.626070040e-34  #
    c = 299792458
    e = 1.602176565e-19

    # in keV * A: 1 m = 10^10 A, 1 keV = 10^3 eV
    hc_over_e = h * c / e * power(10, 10 - 3)
    hc_over_2e = hc_over_e / 2

    # Si lattice parameter in A @ 295.7 K
    # O'Mara, William C. (1990). Handbook of Semiconductor Silicon Technology.
    # William Andrew Inc. pp. 349-352. (Wikipedia 01/2016)
    D_Si = 5.430710
    # Robert Hull (1999). Properties of Crystalline Silicon. INSPEC
    # Y. Okada, pp. 91-92
    D_Si = 5.43102044

    pi_180 = pi / 180.0


def cubic_d_spacing(hkl, d=Constant.D_Si):
    h, k, l = hkl
    return d / sqrt(h ** 2 + k ** 2 + l ** 2)


D_Si_111 = cubic_d_spacing((1, 1, 1))
D_Si_220 = cubic_d_spacing((2, 2, 0))
D_Si_311 = cubic_d_spacing((3, 1, 1))


def bragg_angle(e, d):
    return arcsin(Constant.hc_over_2e / (d * e))


def bragg_energy(th, d):
    return Constant.hc_over_2e / (d * sin(th))


LM_OFF, LM_220, LM_311 = "off", "220", "311"

LM_D_C1 = D_Si_111
LM_D_C2 = {LM_220: D_Si_220, LM_311: D_Si_311}

Default_Geom_Pars = {
    "sample_2_det": 1000.95,
    "sample_2_leg1": 782.86,
    "leg1_2_leg2": 429.86,
    "leg1_2_beam": 706.00,
    "leg2_2_beam": 645.47,
    "table_skew_y": rad2deg(0.053),
}


def calc_lm_2th(liq_mode, e):
    if liq_mode == LM_OFF:
        return 0
    th1 = bragg_angle(e, LM_D_C1)
    th2 = bragg_angle(e, LM_D_C2[liq_mode])
    return 2 * (th2 - th1)


def calc_q(e, th):
    k = 2 * pi * e / Constant.hc_over_e
    return 2 * k * sin(th)


def calc_phys(virt_pos, pars):
    liq_mode = pars["liquid_mode"]
    if liq_mode != LM_OFF:
        lm_2th = calc_lm_2th(liq_mode, pars["beam_energy"])
        sin_lm_2th = sin(lm_2th)
    beam_off = pars["beam_offset"]
    sample_2_det = pars["sample_2_det"]
    sample_2_leg1 = pars["sample_2_leg1"]
    leg1_2_leg2 = pars["leg1_2_leg2"]
    leg1_2_beam = pars["leg1_2_beam"]
    leg2_2_beam = pars["leg2_2_beam"]
    table_skew_y = pars["table_skew_y"]
    sample_2_leg2 = sample_2_leg1 + leg1_2_leg2

    mu = virt_pos["mu"]
    gamma = virt_pos["gamma"]
    delta = virt_pos["delta"]
    dyo = virt_pos["dyo"]
    dzo = virt_pos["dzo"]

    if liq_mode == LM_OFF:
        dty = mu
        ai = mu
        lm_chi = 0
        dd = 0
    else:
        if mu > lm_2th:
            raise ValueError("Error: mu exceeds max. value: " "lm_2th=%s rad" % lm_2th)
        dty = 0
        ai = 0
        lm_chi = arcsin(sin(mu) / sin_lm_2th)
        dd = arcsin(cos(lm_chi) * sin_lm_2th)

    dtz = arcsin(cos(gamma) * sin(delta - dd))
    dty += arcsin(sin(gamma) / cos(dtz))
    dty_slide_factor = 1 / cos(dty) - 1
    tan_dty = tan(dty)

    sample_2_det += sample_2_leg2 * dty_slide_factor - leg2_2_beam * tan_dty
    dy = sample_2_det * tan(dtz) + beam_off + dty * table_skew_y + dyo
    dz1 = sample_2_leg1 * tan_dty - leg1_2_beam * dty_slide_factor + dzo
    dz2 = sample_2_leg2 * tan_dty - leg2_2_beam * dty_slide_factor + dzo

    phys_pos = {"ai": ai, "lmchi": lm_chi, "dy": dy, "dtz": dtz, "dz1": dz1, "dz2": dz2}
    return phys_pos


def calc_virt(phys_pos, pars):
    liq_mode = pars["liquid_mode"]
    if liq_mode != LM_OFF:
        lm_2th = calc_lm_2th(liq_mode, pars["beam_energy"])
        sin_lm_2th = sin(lm_2th)
    beam_off = pars["beam_offset"]
    sample_2_det = pars["sample_2_det"]
    sample_2_leg1 = pars["sample_2_leg1"]
    leg1_2_leg2 = pars["leg1_2_leg2"]
    leg1_2_beam = pars["leg1_2_beam"]
    leg2_2_beam = pars["leg2_2_beam"]
    table_skew_y = pars["table_skew_y"]
    sample_2_leg2 = sample_2_leg1 + leg1_2_leg2

    ai = phys_pos["ai"]
    lm_chi = phys_pos["lmchi"]
    dy = phys_pos["dy"]
    dtz = phys_pos["dtz"]
    dz1 = phys_pos["dz1"]
    dz2 = phys_pos["dz2"]

    # TODO checks:
    #  liq_mode -> ai == 0

    dzo = dz1
    if dz1 == dz2:
        dty = 0
    else:
        A = leg1_2_leg2
        B = leg1_2_beam - leg2_2_beam
        C = (dz2 - dz1) + B
        cplx_roots = roots((B ** 2 - A ** 2, 2 * A * C, B ** 2 - C ** 2))
        real_roots = [x for x in cplx_roots if type(x) == float64]
        tan_dty = min(real_roots)  # to be clarified
        dty = arctan(tan_dty)
        dty_slide_factor = 1 / cos(dty) - 1
        dzo -= sample_2_leg1 * tan_dty - leg1_2_beam * dty_slide_factor
        sample_2_det += sample_2_leg2 * dty_slide_factor - leg2_2_beam * tan_dty

    dyo = dy - (sample_2_det * tan(dtz) + beam_off + dty * table_skew_y)

    if liq_mode == LM_OFF:
        mu = ai
        dd = 0
        dty -= mu
    else:
        mu = arcsin(sin(lm_chi) * sin_lm_2th)
        dd = arcsin(cos(lm_chi) * sin_lm_2th)

    gamma = arcsin(sin(dty) * cos(dtz))
    delta = arcsin(sin(dtz) / cos(gamma)) + dd

    virt_pos = {"mu": mu, "gamma": gamma, "delta": delta, "dyo": dyo, "dzo": dzo}
    return virt_pos


def print_group(pos_dict, name, motors):
    angles = ["mu", "gamma", "delta", "lmchi", "ai", "dtz"]
    print("%s:" % name)
    msg = ""
    for i, motor in enumerate(motors):
        pos = pos_dict[motor]
        if motor in angles:
            pos = rad2deg(pos)
        msg += "  %-7s%10.4f" % ("%s:" % motor, pos)
        if i % 4 == 3:
            print(msg)
            msg = ""
    if msg:
        print(msg)


def print_pos(virt_pos, phys_pos):
    print_group(virt_pos, "Virtual", ["mu", "delta", "gamma", "dyo", "dzo"])
    print_group(phys_pos, "Physical", ["lmchi", "ai", "dy", "dtz", "dz1", "dz2"])


def calc_forward_n_backward(virt_pos, pars):
    phys_pos = calc_phys(virt_pos, pars)
    print_pos(virt_pos, phys_pos)
    new_virt_pos = calc_virt(phys_pos, pars)
    print_pos(new_virt_pos, phys_pos)


def main():
    bl_pars = {"liquid_mode": LM_OFF, "beam_offset": 0, "beam_energy": 40}

    pars = dict(Default_Geom_Pars)
    pars.update(bl_pars)

    virt_pos = {
        "mu": deg2rad(0),
        "gamma": deg2rad(0),
        "delta": deg2rad(0),
        "dyo": 0,
        "dzo": 0,
    }
    calc_forward_n_backward(virt_pos, pars)

    virt_pos["mu"] = deg2rad(30)
    virt_pos["gamma"] = deg2rad(12.3456)
    calc_forward_n_backward(virt_pos, pars)

    virt_pos["mu"] = deg2rad(-30)
    virt_pos["delta"] = deg2rad(-24.6810)
    calc_forward_n_backward(virt_pos, pars)

    virt_pos["dyo"] = 123.4567
    virt_pos["dzo"] = -456.7891
    calc_forward_n_backward(virt_pos, pars)


if __name__ == "__main__":
    main()
