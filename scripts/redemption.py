#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
conversion script to change SPEC config into bliss configuration
"""

__author__ = "cyril.guilloud@esrf.fr"
__date__ = "2015"
__version__ = 0.1

from SpecConfig.SpecCatalog import *
import SpecConfig
import SpecConfig.ConfigFile


def isIcepapCtrl(ctrl):
    if ctrl.id == "PSE_MAC_MOT" and ctrl.pars[0] == "icepap":
        return True
    else:
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage : %s <spec_config_file>" % sys.argv[0])
        sys.exit()

    config = SpecConfig.ConfigFile.ConfigFile(sys.argv[1])

    # prints config
    # config.save()

    controllers = dict()
    ii = 0

    for controller in config.controllers:
        if isIcepapCtrl(controller):
            controllers[ii] = ("icepap", controller.pars[2])
        else:
            controllers[ii] = ("ctrl", "")
        ii += 1

    print("---------- icepap controllers ------------------------")
    print(controllers)

    for ictrl in controllers:
        print(ictrl, ":", controllers[ictrl])
    print("----------------------------------------------------")

    print("---------- icepap motors  ------------------------")
    for mot in config.motors:
        if mot.pars["controller"] == "MAC_MOT":
            if controllers[mot.pars["unit"]][0] == "icepap":
                print(mot.pars)


"""

from  SpecConfig.SpecCatalog  import *
import SpecConfig
import SpecConfig.ConfigFile
config = SpecConfig.ConfigFile.ConfigFile("/users/blissadm/local/spec/spec.d/cyril/config")
cc = config.controllers[1]



"""
