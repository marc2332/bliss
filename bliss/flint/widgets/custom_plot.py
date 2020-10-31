# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import logging

from silx.gui import qt


_logger = logging.getLogger(__name__)


class CustomPlot(qt.QWidget):
    def __init__(self, parent=None):
        super(CustomPlot, self).__init__(parent=parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.__plot = None
        self.__plotId = None
        self.__name = None

    def setName(self, name):
        self.__name = name

    def name(self):
        return self.__name

    def setPlotId(self, plotId):
        self.__plotId = plotId

    def plotId(self):
        return self.__plotId

    def setPlot(self, plot):
        layout = self.layout()
        layout.addWidget(plot)
        self.__plot = plot

    def _silxPlot(self):
        return self.__plot
