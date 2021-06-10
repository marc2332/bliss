# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import numpy

from silx.gui import qt
from silx.gui import plot as silx_plot


class _DataWidget(qt.QWidget):
    def __init__(self, parent=None):
        super(_DataWidget, self).__init__(parent=parent)
        layout = qt.QVBoxLayout(self)
        self.__silxWidget = self._createSilxWidget(self)
        layout.addWidget(self.__silxWidget)
        self.__dataDict = {}

    def dataDict(self):
        return self.__dataDict

    def silxWidget(self):
        return self.__silxWidget

    def silxPlot(self):
        """Used by the interactive API.

        This have to returns a PlotWidget, that's why it could be not always
        the same as the silx widget.
        """
        return self.__silxWidget

    def _createSilxWidget(self, parent):
        raise NotImplementedError

    def __getattr__(self, name: str):
        silxWidget = self.silxWidget()
        return getattr(silxWidget, name)


class Plot1D(_DataWidget):
    """Generic plot to display 1D data"""

    def _createSilxWidget(self, parent):
        return silx_plot.Plot1D(parent=parent)


class Plot2D(_DataWidget):
    """Generic plot to display 2D data"""

    def _createSilxWidget(self, parent):
        return silx_plot.Plot2D(parent=parent)

    def setDisplayedIntensityHistogram(self, show):
        self.getIntensityHistogramAction().setVisible(show)


class ImageView(_DataWidget):
    """Dedicated plot to display an image"""

    def _createSilxWidget(self, parent):
        return silx_plot.ImageView(parent=parent)

    def setDisplayedIntensityHistogram(self, show):
        self.getIntensityHistogramAction().setVisible(show)


class ScatterView(_DataWidget):
    """Dedicated plot to display a 2D scatter"""

    def _createSilxWidget(self, parent):
        return silx_plot.ScatterView(parent=parent)

    def getDataRange(self):
        plot = self.silxWidget().getPlotWidget()
        return plot.getDataRange()

    def clear(self):
        self.silxWidget().setData(None, None, None)

    def setData(
        self, x, y, value, xerror=None, yerror=None, alpha=None, resetzoom=True
    ):
        self.silxWidget().setData(
            x, y, value, xerror=xerror, yerror=yerror, alpha=alpha, copy=False
        )
        if resetzoom:
            # Else the view is not updated
            self.resetZoom()


class StackImageView(_DataWidget):
    """Dedicated plot to display a stack of images"""

    def _createSilxWidget(self, parent):
        return silx_plot.StackView(parent=parent)

    def getDataRange(self):
        plot = self.silxWidget().getPlotWidget()
        return plot.getDataRange()
