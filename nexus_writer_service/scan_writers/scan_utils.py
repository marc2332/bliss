# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os


def scan_name(info, subscan=1):
    """
    :param bliss.scanning.scan.Scan or dict scan_info:
    :returns str:
    """
    if not isinstance(info, dict):
        info = info.scan_info
    return '{}.{}'.format(info['scan_nb'], subscan)


def scan_filename(filename=None):
    """
    :param str filename:
    :returns str:
    """
    if filename and filename != '<no saving>':
        return os.path.splitext(filename)[0] + "_external.h5"
    else:
        return 'data_external.h5'
