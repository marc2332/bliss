#-*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import warnings
import logging
import weakref

try:
    from PyQt4.QtCore import pyqtRemoveInputHook
except ImportError:
    from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import plot as silx_plot
    from silx.gui import qt

Plot1D = silx_plot.Plot1D

class LivePlot1D(qt.QWidget):
    def __init__(self, *args, **kw):
        self._data_dict = kw.pop("data_dict")
        self.plot_id = None #filled by caller

        qt.QWidget.__init__(self, *args, **kw)

        self._enabled_plots = dict()
        self._curves = dict()

        self.axes_selection = qt.QWidget(self)
        self.x_axis = qt.QComboBox(self.axes_selection)
        self.y_axis = qt.QComboBox(self.axes_selection)
        self.add_plot = qt.QPushButton("Add plot", self.axes_selection)
        self.silx_plot = silx_plot.Plot1D(self)

        qt.QHBoxLayout(self.axes_selection)
        self.axes_selection.layout().addWidget(qt.QLabel("X axis: ",
                                                         self.axes_selection))
        self.axes_selection.layout().addWidget(self.x_axis)
        self.axes_selection.layout().addWidget(qt.QLabel("Y axis: ",
                                                         self.axes_selection))
        self.axes_selection.layout().addWidget(self.y_axis)
        self.axes_selection.layout().addWidget(self.add_plot)
        self.axes_selection.layout().addSpacerItem(qt.QSpacerItem(1,1,qt.QSizePolicy.Expanding,
                                                                  qt.QSizePolicy.Minimum))
 
        qt.QVBoxLayout(self)
        self.layout().addWidget(self.axes_selection)
        self.layout().addWidget(self.silx_plot)

        self.add_plot.setEnabled(False)
        self.x_axis.activated[str].connect(self._x_axis_selected)
        self.y_axis.activated[str].connect(self._y_axis_selected)
        self.add_plot.clicked.connect(self._add_plot)

    def _get_data(self, x_axis, y_axis):
        data_len = self._enabled_plots[(x_axis, y_axis)]
        x_data = self._data_dict[self.plot_id].get(x_axis)
        y_data = self._data_dict[self.plot_id].get(y_axis)
        if x_data is None or y_data is None:
            return None, None
        return x_data[:data_len], y_data[:data_len]

    def __getattr__(self, attr):
        """Delegate to silx plot widget"""
        if attr.startswith("__"):
            raise AttributeError
        return getattr(self.silx_plot, attr)

    def set_x_axes(self, axis_names_list):
        self.x_axis.clear()
        for axis_names in list(self._enabled_plots.keys()):
            if axis_names[0] not in axis_names_list:
                x_axis, y_axis = axis_names
                legend = '%s -> %s' % (x_axis, y_axis)
                del self._enabled_plots[(x_axis, y_axis)]
                self.silx_plot.removeCurve(legend)
            else:
                self._enabled_plots[axis_names] = 0
        self.x_axis.addItems(axis_names_list)

    def set_y_axes(self, axis_names_list):
        self.y_axis.clear()
        for axis_names in list(self._enabled_plots.keys()):
            if axis_names[1] not in axis_names_list:
                x_axis, y_axis = axis_names
                legend = '%s -> %s' % (x_axis, y_axis)
                del self._enabled_plots[(x_axis, y_axis)]
                self.silx_plot.removeCurve(legend)
            else:
                self._enabled_plots[axis_names] = 0
        self.y_axis.addItems(axis_names_list)

    def _x_axis_selected(self, x_axis):
        y_axis = self.y_axis.currentText()
        self.add_plot.setEnabled((x_axis, y_axis) in self._enabled_plots)

    def _y_axis_selected(self, y_axis):
        x_axis = self.x_axis.currentText()
        self.add_plot.setEnabled((x_axis, y_axis) in self._enabled_plots)

    def enable(self, x_axis_name, y_axis_name, data_len):
        self._enabled_plots[(x_axis_name, y_axis_name)] = data_len
        x_axis = self.x_axis.currentText()
        y_axis = self.y_axis.currentText()
        self.add_plot.setEnabled((x_axis, y_axis) in self._enabled_plots)

    def _add_plot(self):
        x_axis = self.x_axis.currentText()
        y_axis = self.y_axis.currentText()
        legend = '%s -> %s' % (x_axis, y_axis)
        x_data, y_data = self._get_data(x_axis, y_axis)
        self.silx_plot.addCurve(x_data, y_data, legend=legend, copy=False)

    def close(self):
        for plot in self._curves.keys():
            self._curves[plot] = 0
 
    def update_plots(self):
        for axis_names, data_len in self._enabled_plots.iteritems():
            x_axis, y_axis = axis_names
            legend = '%s -> %s' % (x_axis, y_axis)
            plot = self.silx_plot.getCurve(legend)
            if plot is not None:
                # plot is displayed
                if self._curves.get(plot, 0) < data_len:
                    # update plot
                    x_data, y_data = self._get_data(x_axis, y_axis)
                    if x_data is not None:
                        self._curves[plot] = data_len
                        self.silx_plot.addCurve(x_data, y_data, legend=legend, copy=False)

