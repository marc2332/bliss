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


class Plot1D(silx_plot.Plot1D):
    """Generic plot to display 1D data"""


class Plot2D(silx_plot.Plot2D):
    """Generic plot to display 2D data"""

    def setDisplayedIntensityHistogram(self, show):
        self.getIntensityHistogramAction().setVisible(show)


class ImageView(silx_plot.ImageView):
    """Dedicated plot to display an image"""

    def setDisplayedIntensityHistogram(self, show):
        self.getIntensityHistogramAction().setVisible(show)


class ScatterView(silx_plot.ScatterView):
    """Dedicated plot to display a 2D scatter"""

    def getDataRange(self):
        plot = self.getPlotWidget()
        return plot.getDataRange()

    def setData(
        self, x, y, value, xerror=None, yerror=None, alpha=None, resetzoom=True
    ):
        super(ScatterView, self).setData(
            x, y, value, xerror=xerror, yerror=yerror, alpha=alpha, copy=False
        )
        if resetzoom:
            # Else the view is not updated
            self.resetZoom()


class StackImageView(silx_plot.StackView):
    """Dedicated plot to display a stack of images"""

    def getDataRange(self):
        plot = self.getPlotWidget()
        return plot.getDataRange()
