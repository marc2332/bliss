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
        self.__data = {}
        self.__methods = {}

    def setName(self, name):
        self.__name = name

    def name(self):
        return self.__name

    def setPlotId(self, plotId):
        self.__plotId = plotId

    def plotId(self):
        return self.__plotId

    def setPlot(self, plot: qt.QWidget):
        """
        Set a plot to this custom plot holder.
        """
        # FIXME: Remove the previous one if there was one
        layout = self.layout()
        layout.addWidget(plot)
        self.__plot = plot

    def _silxPlot(self):
        return self.__plot

    def registerMethod(self, method_id, method):
        if method_id in self.__methods:
            raise ValueError(f"Method {method_id} already registred")
        self.__methods[method_id] = method

    def runMethod(self, method_id, args, kwargs):
        method = self.__methods.get(method_id)
        if method_id is None:
            plot_id = self.plotId()
            raise ValueError(
                "Method '%s' on plot id '%s' is unknown", method_id, plot_id
            )
        return method(self, self.__plot, self.__data, args, kwargs)

    def updateData(self, field, data):
        self.__data[field] = data

    def removeData(self, field):
        del self.__data[field]

    def getData(self, field=None):
        if field is None:
            return self.__data
        else:
            return self.__data.get(field, [])

    def selectData(self, method, names, kwargs):
        # FIXME: method is not needed, that's ugly
        # FIXME: kwargs is not a good idea
        # Hackish legend handling
        if "legend" not in kwargs and method.startswith("add"):
            kwargs["legend"] = " -> ".join(names)
        # Get the data to plot
        args = tuple(self.__data[name] for name in names)
        method = getattr(self.__plot, method)
        # Plot
        method(*args, **kwargs)

    def deselectData(self, names):
        legend = " -> ".join(names)
        self.__plot.remove(legend)

    def clearData(self):
        self.__data.clear()
        self.__plot.clear()
