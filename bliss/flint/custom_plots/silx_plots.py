# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

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

    def updateStoredData(self, field, data):
        data_dict = self.dataDict()

        # Data from the network is sometime not writable
        # This make it fail silx for some use cases
        if data is None:
            return None
        if isinstance(data, numpy.ndarray):
            if not data.flags.writeable:
                data = numpy.array(data)

        data_dict[field] = data

    def removeStoredData(self, field):
        data_dict = self.dataDict()
        del data_dict[field]

    def getStoredData(self, field=None):
        data_dict = self.dataDict()
        if field is None:
            return data_dict
        else:
            return data_dict.get(field, [])

    def clearStoredData(self):
        data_dict = self.dataDict()
        data_dict.clear()

    def clear(self):
        self.clearStoredData()
        self.silxWidget().clear()

    def selectStoredData(self, *names, **kwargs):
        # FIXME: This have to be moved per plot widget
        # FIXME: METHOD have to be removed
        method = self.METHOD
        if "legend" not in kwargs and method.startswith("add"):
            kwargs["legend"] = " -> ".join(names)
        data_dict = self.dataDict()
        args = tuple(data_dict[name] for name in names)
        widget_method = getattr(self, method)
        # Plot
        widget_method(*args, **kwargs)

    def deselectStoredData(self, *names):
        legend = " -> ".join(names)
        self.remove(legend)


class Plot1D(_DataWidget):
    """Generic plot to display 1D data"""

    # Name of the method to add data to the plot
    METHOD = "addCurve"

    def _createSilxWidget(self, parent):
        widget = silx_plot.Plot1D(parent=parent)
        widget.setDataMargins(0.05, 0.05, 0.05, 0.05)
        return widget


class Plot2D(_DataWidget):
    """Generic plot to display 2D data"""

    # Name of the method to add data to the plot
    METHOD = "addImage"

    def _createSilxWidget(self, parent):
        widget = silx_plot.Plot2D(parent=parent)
        widget.setDataMargins(0.05, 0.05, 0.05, 0.05)
        return widget

    def setDisplayedIntensityHistogram(self, show):
        self.getIntensityHistogramAction().setVisible(show)


class ImageView(_DataWidget):
    """Dedicated plot to display an image"""

    # Name of the method to add data to the plot
    METHOD = "setImage"

    def _createSilxWidget(self, parent):
        widget = silx_plot.ImageView(parent=parent)
        widget.setDataMargins(0.05, 0.05, 0.05, 0.05)
        return widget

    def setDisplayedIntensityHistogram(self, show):
        self.getIntensityHistogramAction().setVisible(show)


class ScatterView(_DataWidget):
    """Dedicated plot to display a 2D scatter"""

    # Name of the method to add data to the plot
    METHOD = "setData"

    def _createSilxWidget(self, parent):
        widget = silx_plot.ScatterView(parent=parent)
        plot = widget.getPlotWidget()
        plot.setDataMargins(0.05, 0.05, 0.05, 0.05)
        return widget

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

    # Name of the method to add data to the plot
    METHOD = "setStack"

    def _createSilxWidget(self, parent):
        return silx_plot.StackView(parent=parent)

    def getDataRange(self):
        plot = self.silxWidget().getPlotWidget()
        return plot.getDataRange()
