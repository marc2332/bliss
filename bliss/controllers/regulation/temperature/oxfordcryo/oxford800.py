# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from .oxford700 import Oxford700


class Oxford800(Oxford700):
    def __init__(self, config):
        super().__init__(config)
