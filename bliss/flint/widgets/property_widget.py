# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

from silx.gui import qt


class MainPropertyWidget(qt.QDockWidget):
    def __init__(self, parent: qt.QWidget = None):
        super(MainPropertyWidget, self).__init__(parent=parent)
        self.setObjectName("scan-property-widget")
        self.setWindowTitle("Plot properties")
