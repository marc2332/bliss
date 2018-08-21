# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Repository of motor controllers

.. autosummary::
    :toctree:

    calc_motor_mockup
    energy_wl
    flexdc
    galildmc213
    icepap
    id16beam
    id31diffractlintilt
    id31diffract
    kb
    md2
    mockup
    nf8753
    pi_c663
    pi_e517
    pi_e51x
    pi_e712
    pi_e753
    pi_e871
    pi_gcs
    pm600
    pmd206
    setpoint
    slitbox
    slits
    spectro_eh1_test_v1
    spectro_eh1_test_v2
    tab3
    tabsup
    tangoemot
    template
    trans4
    undulator
    vscanner
"""
__all__ = []


def _init_module():
    import os

    for root, dirs, files in os.walk(__path__[0], followlinks=True):
        for file_name in files:
            if file_name.startswith("__"):
                continue
            base, ext = os.path.splitext(file_name)
            if ext == ".py":
                subdir = root[len(__path__[0]) + 1 :]
                if subdir:
                    base = "%s.%s" % (subdir, base)
                __all__.append(base)


_init_module()
