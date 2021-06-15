# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import typing
import numpy
import logging

from silx.gui import qt
from silx.gui import plot as silx_plot

_logger = logging.getLogger(__name__)


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

    class CurveItem(typing.NamedTuple):
        xdata: str
        ydata: str
        style: typing.Dict[str, object]

    def __init__(self, parent=None):
        _DataWidget.__init__(self, parent=parent)
        self.__items = {}
        self.__autoUpdatePlot = True
        self.__raiseOnException = False

    def setRaiseOnException(self, raises):
        """To simplify remote debug"""
        self.__raiseOnException = raises

    def _createSilxWidget(self, parent):
        widget = silx_plot.Plot1D(parent=parent)
        widget.setDataMargins(0.05, 0.05, 0.05, 0.05)
        return widget

    def setAutoUpdatePlot(self, update="bool"):
        """Set to true to enable or disable update of plot for each changes of
        the data or items"""
        self.__autoUpdatePlot = update

    def clearItems(self):
        """Remove the item definitions"""
        self.__items.clear()
        self.__updatePlotIfNeeded()

    def removeItem(self, legend: str):
        """Remove a specific item by name"""
        del self.__items[legend]
        self.__updatePlotIfNeeded()

    def addCurveItem(self, xdata: str, ydata: str, legend: str = None, **kwargs):
        """Define an item which have to be displayed with the specified data
        name
        """
        if legend is None:
            legend = ydata + " -> " + xdata
        self.__items[legend] = self.CurveItem(xdata, ydata, kwargs)
        self.__updatePlotIfNeeded()

    def setData(self, **kwargs):
        dataDict = self.dataDict()
        for k, v in kwargs.items():
            dataDict[k] = v
        self.__updatePlotIfNeeded()

    def appendData(self, **kwargs):
        dataDict = self.dataDict()
        for k, v in kwargs.items():
            d = dataDict.get(k, None)
            if d is None:
                d = v
            else:
                d = numpy.concatenate((d, v))
            dataDict[k] = d
        self.__updatePlotIfNeeded()

    def clear(self):
        super(Plot1D, self).clear()
        self.__updatePlotIfNeeded()

    def updatePlot(self, resetzoom: bool = True):
        try:
            self.__updatePlot()
        except Exception:
            _logger.error("Error while updating the plot", exc_info=True)
            if self.__raiseOnException:
                raise
        if resetzoom:
            self.resetZoom()

    def __updatePlotIfNeeded(self):
        if self.__autoUpdatePlot:
            self.updatePlot(resetzoom=True)

    def __updatePlot(self):
        plot = self.silxPlot()
        plot.clear()
        dataDict = self.dataDict()
        for legend, item in self.__items.items():
            xData = dataDict.get(item.xdata)
            yData = dataDict.get(item.ydata)
            if xData is None or yData is None:
                continue
            if len(yData) != len(xData):
                size = min(len(yData), len(xData))
                xData = xData[0:size]
                yData = yData[0:size]
            if len(yData) == 0:
                continue
            plot.addCurve(xData, yData, legend=legend, **item.style, resetzoom=False)


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
