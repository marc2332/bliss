
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os.path
from ast import literal_eval


def get_nanodac_cmds():

    __fpath = os.path.realpath(__file__)
    __fdir = os.path.dirname(__fpath)
    fpath = os.path.join(__fdir, "nanodac_cmds.txt")
    txt = open(fpath, "r").read()
    cmds = literal_eval(txt)

    return cmds
