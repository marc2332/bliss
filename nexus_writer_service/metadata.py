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

import enum
from bliss.scanning import scan_meta
from .subscribers import scan_writer_publish

GENERATORS = {"writer_config": scan_writer_publish}


def register_all_metadata_generators(force=False):
    """
    Register all metadata generators in a bliss session for
    the scan writers (currently only one).

    :param bool force: re-initialize when already done
    """
    kwargs = {k: True for k in GENERATORS}
    register_metadata_categories(force=force, **kwargs)
    register_metadata_generators(**kwargs)


def register_metadata_generators(**kwargs):
    """
    Register metadata generators in a bliss session for
    the scan writers (currently only one).

    :param **kwargs: any key of `GENERATORS`
    """
    # Generators are called at the start of the scan:
    #   bliss.scanning.scan.Scan.__init__
    # and at the end of the scan
    #   run bliss.scanning.scan.Scan.run (cleanup section)
    #
    # The generator 'instrument.positioners' is an exception.
    # It is only called at the beginning of the scan by
    # removing it before calling the generators a second time.
    generators = scan_meta.get_user_scan_meta()
    for k, mod in GENERATORS.items():
        if kwargs.get(k, False):
            mod.register_metadata_generators(generators)


def register_metadata_categories(force=False, **kwargs):
    """
    Register metadata categories in a bliss session for
    the scan writers (currently only one).

    :param bool force: re-initialize when already done
    :param **kwargs: any key of `GENERATORS`
    """
    # Add custom categories
    generators = scan_meta.get_user_scan_meta()
    categories = {m.name for m in scan_meta.CATEGORIES}
    for k, mod in GENERATORS.items():
        if kwargs.get(k, False):
            categories |= set(mod.CATEGORIES)
    try:
        if force:
            raise AttributeError
        for attr in categories:
            getattr(generators, attr.lower())
    except AttributeError:
        scan_meta.CATEGORIES = enum.Enum(
            scan_meta.CATEGORIES.__name__, list(categories)
        )
        scan_meta.USER_SCAN_META = scan_meta.scan_meta()
