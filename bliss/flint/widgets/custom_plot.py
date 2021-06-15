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
    """
    Widget holder to contain plot managed by BLISS.

    It provides few helpers to identify and interact with it.
    """

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

    def logger(self):
        global _logger
        return _logger

    def widget(self):
        return self.__plot

    def setPlot(self, plot: qt.QWidget):
        """
        Set a plot to this custom plot holder.
        """
        # FIXME: Remove the previous one if there was one
        layout = self.layout()
        layout.addWidget(plot)
        self.__plot = plot

    def defaultColormap(self):
        plot = self.__plot
        if plot is None:
            return None
        if hasattr(plot, "getColormap"):
            return plot.getColormap()
        return None

    def _silxPlot(self):
        plot = self.__plot
        if hasattr(plot, "silxPlot"):
            return plot.silxPlot()
        return plot
