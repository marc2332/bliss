# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


class Shutter:
    def __init__(self, controller, proxy):
        self._proxy = proxy

    @property
    def proxy(self):
        return self._proxy

    def open(self):
        self._proxy.openShutterManual()

    def close(self):
        self._proxy.closeShutterManual()
