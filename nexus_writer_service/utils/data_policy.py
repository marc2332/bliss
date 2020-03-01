# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
ESRF data policy unofficial (but still valid)
"""

import os


def masterfile_templates():
    """
    Templates for HDF5 file names relative to the dataset directory

    :returns dict(str):
    """
    return {
        "sample": os.path.join(
            "..", os.path.extsep.join(("{proposal}_{sample}", "h5"))
        ),
        "proposal": os.path.join(
            "..", "..", os.path.extsep.join(("{proposal}_{beamline}", "h5"))
        ),
    }
