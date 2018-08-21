# -*- coding: utf-8 -*-
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
    from silx.gui.plot.Colormap import Colormap
    from silx.gui import qt

Plot1D = silx_plot.Plot1D


class LivePlot1D(qt.QWidget):
    def __init__(self, *args, **kw):
        self._data_dict = kw.pop("data_dict")
        self.plot_id = None  # filled by caller

        qt.QWidget.__init__(self, *args, **kw)

        self._enabled_plots = dict()
        self._curves = dict()

        self.axes_selection = qt.QWidget(self)
        self.x_axis = qt.QComboBox(self.axes_selection)
        self.y_axis = qt.QComboBox(self.axes_selection)
        self.add_plot = qt.QPushButton("Add curve", self.axes_selection)
        self.silx_plot = silx_plot.Plot1D(self)

        qt.QHBoxLayout(self.axes_selection)
        self.axes_selection.layout().addWidget(
            qt.QLabel("X axis: ", self.axes_selection)
        )
        self.axes_selection.layout().addWidget(self.x_axis)
        self.axes_selection.layout().addWidget(
            qt.QLabel("Y axis: ", self.axes_selection)
        )
        self.axes_selection.layout().addWidget(self.y_axis)
        self.axes_selection.layout().addWidget(self.add_plot)
        self.axes_selection.layout().addSpacerItem(
            qt.QSpacerItem(1, 1, qt.QSizePolicy.Expanding, qt.QSizePolicy.Minimum)
        )

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
                legend = "%s -> %s" % (x_axis, y_axis)
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
                legend = "%s -> %s" % (x_axis, y_axis)
                del self._enabled_plots[(x_axis, y_axis)]
                self.silx_plot.removeCurve(legend)
            else:
                self._enabled_plots[axis_names] = 0
        self.y_axis.addItems(axis_names_list)

    def _x_axis_selected(self, x_axis):
        self.update_add_plot_button()

    def _y_axis_selected(self, y_axis):
        self.update_add_plot_button()

    def update_add_plot_button(self):
        x_axis = self.x_axis.currentText()
        y_axis = self.y_axis.currentText()
        enabled = self._enabled_plots.get((x_axis, y_axis), 0) > 0
        self.add_plot.setEnabled(enabled)

    def _add_plot(self):
        x_axis = self.x_axis.currentText()
        y_axis = self.y_axis.currentText()
        legend = "%s -> %s" % (x_axis, y_axis)
        x_data, y_data = self._get_data(x_axis, y_axis)
        curve = self.silx_plot.getCurve(legend)
        if curve:
            curve.setData(x_data, y_data, copy=False)
        else:
            self.silx_plot.addCurve(x_data, y_data, legend=legend, copy=False)

    @property
    def x_axis_names(self):
        for i in range(len(self.x_axis)):
            yield self.x_axis.itemText(i)

    @property
    def y_axis_names(self):
        for i in range(len(self.y_axis)):
            yield self.y_axis.itemText(i)

    def update_enabled_plots(self):
        for x_axis in self.x_axis_names:
            for y_axis in self.y_axis_names:
                x_data = self._data_dict[self.plot_id].get(x_axis, [])
                y_data = self._data_dict[self.plot_id].get(y_axis, [])
                data_len = min(len(x_data), len(y_data))
                self._enabled_plots[(x_axis, y_axis)] = data_len

    def update_plots(self):
        for axis_names, data_len in self._enabled_plots.iteritems():
            x_axis, y_axis = axis_names
            legend = "%s -> %s" % (x_axis, y_axis)
            plot = self.silx_plot.getCurve(legend)
            if plot is not None:
                # plot is displayed
                if self._curves.get(plot, 0) > data_len:
                    # existing curve need to be removed
                    self._curves[plot] = 0
                if self._curves.get(plot, 0) < data_len:
                    # update plot
                    x_data, y_data = self._get_data(x_axis, y_axis)
                    if x_data is not None:
                        self._curves[plot] = data_len
                        self.silx_plot.addCurve(
                            x_data, y_data, legend=legend, copy=False
                        )

    def update_all(self):
        self.update_enabled_plots()
        self.update_add_plot_button()
        self.update_plots()

    def addXMarker(self, *args, **kwargs):
        return self.silx_plot.addXMarker(*args, **kwargs)


# Ugly copy paste! Shame!


class LiveScatterPlot(qt.QWidget):
    def __init__(self, *args, **kw):
        self._data_dict = kw.pop("data_dict")
        self.plot_id = None  # filled by caller

        qt.QWidget.__init__(self, *args, **kw)

        self._margin = 0.1
        self._enabled_plots = dict()
        self._curves = dict()

        self.axes_selection = qt.QWidget(self)
        self.x_axis = qt.QComboBox(self.axes_selection)
        self.y_axis = qt.QComboBox(self.axes_selection)
        self.z_axis = qt.QComboBox(self.axes_selection)
        self.add_plot = qt.QPushButton("Add plot", self.axes_selection)
        self.silx_plot = silx_plot.Plot1D(self)

        qt.QHBoxLayout(self.axes_selection)
        self.axes_selection.layout().addWidget(
            qt.QLabel("X axis: ", self.axes_selection)
        )
        self.axes_selection.layout().addWidget(self.x_axis)
        self.axes_selection.layout().addWidget(
            qt.QLabel("Y axis: ", self.axes_selection)
        )
        self.axes_selection.layout().addWidget(self.y_axis)
        self.axes_selection.layout().addWidget(
            qt.QLabel("Z axis: ", self.axes_selection)
        )
        self.axes_selection.layout().addWidget(self.z_axis)
        self.axes_selection.layout().addWidget(self.add_plot)
        self.axes_selection.layout().addSpacerItem(
            qt.QSpacerItem(1, 1, qt.QSizePolicy.Expanding, qt.QSizePolicy.Minimum)
        )

        qt.QVBoxLayout(self)
        self.layout().addWidget(self.axes_selection)
        self.layout().addWidget(self.silx_plot)

        self.add_plot.setEnabled(False)
        callback = lambda _: self.update_add_plot_button()
        self.x_axis.activated[str].connect(callback)
        self.y_axis.activated[str].connect(callback)
        self.y_axis.activated[str].connect(callback)
        self.add_plot.clicked.connect(self._add_plot)

    def _get_data(self, x_axis, y_axis, z_axis):
        x_data = self._data_dict[self.plot_id].get(x_axis, [])
        y_data = self._data_dict[self.plot_id].get(y_axis, [])
        z_data = self._data_dict[self.plot_id].get(z_axis, [])
        data_len = min(map(len, (x_data, y_data, z_data)))
        return x_data[:data_len], y_data[:data_len], z_data[:data_len]

    def _get_data_length(self, x_axis, y_axis, z_axis):
        x_data = self._data_dict[self.plot_id].get(x_axis, [])
        y_data = self._data_dict[self.plot_id].get(y_axis, [])
        z_data = self._data_dict[self.plot_id].get(z_axis, [])
        return min(map(len, (x_data, y_data, z_data)))

    def __getattr__(self, attr):
        """Delegate to silx plot widget"""
        if attr.startswith("__"):
            raise AttributeError
        return getattr(self.silx_plot, attr)

    def set_x_axes(self, axis_names_list):
        self.x_axis.clear()
        for axis_names in list(self._enabled_plots.keys()):
            if axis_names[0] not in axis_names_list:
                x_axis, y_axis, z_axis = axis_names
                legend = "%s -> %s -> %s" % (x_axis, y_axis, z_axis)
                del self._enabled_plots[(x_axis, y_axis, z_axis)]
                self.silx_plot.removeCurve(legend)
            else:
                self._enabled_plots[axis_names] = 0
        self.x_axis.addItems(axis_names_list)

    def set_y_axes(self, axis_names_list):
        self.y_axis.clear()
        for axis_names in list(self._enabled_plots.keys()):
            if axis_names[1] not in axis_names_list:
                x_axis, y_axis, z_axis = axis_names
                legend = "%s -> %s -> %s" % (x_axis, y_axis, z_axis)
                del self._enabled_plots[(x_axis, y_axis, z_axis)]
                self.silx_plot.removeCurve(legend)
            else:
                self._enabled_plots[axis_names] = 0
        self.y_axis.addItems(axis_names_list)
        if len(axis_names_list) >= 2:
            self.y_axis.setCurrentIndex(1)

    def set_z_axes(self, axis_names_list):
        self.z_axis.clear()
        for axis_names in list(self._enabled_plots.keys()):
            if axis_names[2] not in axis_names_list:
                x_axis, y_axis, z_axis = axis_names
                legend = "%s -> %s -> %s" % (x_axis, y_axis, z_axis)
                del self._enabled_plots[(x_axis, y_axis, z_axis)]
                self.silx_plot.removeCurve(legend)
            else:
                self._enabled_plots[axis_names] = 0
        self.z_axis.addItems(axis_names_list)

    def update_add_plot_button(self):
        x_axis = self.x_axis.currentText()
        y_axis = self.y_axis.currentText()
        z_axis = self.z_axis.currentText()
        enabled = self._enabled_plots.get((x_axis, y_axis, z_axis), 0) > 0
        self.add_plot.setEnabled(enabled)

    def _add_plot(self):
        x_axis = self.x_axis.currentText()
        y_axis = self.y_axis.currentText()
        z_axis = self.z_axis.currentText()
        legend = "%s -> %s -> %s" % (x_axis, y_axis, z_axis)
        x_data, y_data, z_data = self._get_data(x_axis, y_axis, z_axis)
        self.add_scatter(x_data, y_data, z_data, legend=legend)

    @property
    def x_axis_names(self):
        for i in range(len(self.x_axis)):
            yield self.x_axis.itemText(i)

    @property
    def y_axis_names(self):
        for i in range(len(self.y_axis)):
            yield self.y_axis.itemText(i)

    @property
    def z_axis_names(self):
        for i in range(len(self.z_axis)):
            yield self.z_axis.itemText(i)

    def update_enabled_plots(self):
        for x_axis in self.x_axis_names:
            for y_axis in self.y_axis_names:
                for z_axis in self.z_axis_names:
                    data_length = self._get_data_length(x_axis, y_axis, z_axis)
                    self._enabled_plots[(x_axis, y_axis, z_axis)] = data_length

    def update_plots(self):
        for axis_names, data_len in self._enabled_plots.iteritems():
            x_axis, y_axis, z_axis = axis_names
            legend = "%s -> %s -> %s" % (x_axis, y_axis, z_axis)
            plot = self.silx_plot.getScatter(legend)
            if plot is not None:
                # plot is displayed
                if self._curves.get(plot, 0) > data_len:
                    # existing curve need to be removed
                    self._curves[plot] = 0
                if self._curves.get(plot, 0) < data_len:
                    # update plot
                    x_data, y_data, z_data = self._get_data(x_axis, y_axis, z_axis)
                    self._curves[plot] = data_len
                    self.add_scatter(x_data, y_data, z_data, legend)

    def add_scatter(self, x, y, z, legend):
        current = self.silx_plot.getScatter()
        if current is not None and current.getLegend() != legend:
            self.remove(kind="scatter")
        self.silx_plot.getDefaultColormap().setName("viridis")
        self.silx_plot.addScatter(x, y, z, legend=legend, copy=False, symbol="s")
        self.silx_plot.resetZoom((self._margin,) * 4)
        _, _, w, h = self.silx_plot.getPlotBoundsInPixels()
        pixels = min(w / len(set(x)), h / len(set(y)))
        current = self.silx_plot.getScatter()
        current.setSymbolSize(pixels * 25)
        self.silx_plot.getColorBarWidget().setVisible(True)

    def update_all(self):
        self.update_enabled_plots()
        self.update_add_plot_button()
        self.update_plots()
