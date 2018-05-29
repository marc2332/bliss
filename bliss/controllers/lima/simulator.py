# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .properties import LimaProperty

class Camera(object):
    def __init__(self, name, lima, proxy):
        pass

    @LimaProperty
    def test(self):
        return "test"

