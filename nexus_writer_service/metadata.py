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
Register metadata generators for a configurable writer
"""

from bliss.scanning import scan_meta
from .subscribers import scan_writer_publish

GENERATORS = {"writer_config": scan_writer_publish}


def register_all_metadata_generators():
    """Register all metadata generators in a bliss session for
    the scan writers (currently only one).
    """
    user_scan_meta = scan_meta.get_user_scan_meta()
    for k, mod in GENERATORS.items():
        mod.register_metadata_generators(user_scan_meta)
