# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import warnings
import logging
import weakref
import redis
import numpy
from bliss.config.conductor.client import get_cache_address

try:
    from PyQt4.QtCore import pyqtRemoveInputHook
except ImportError:
    from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import plot as silx_plot
    from silx.gui.plot.Colormap import Colormap
    from silx.gui import qt, colors
    from silx.gui.plot import LegendSelector

Plot1D = silx_plot.Plot1D
REDIS_CACHE = get_cache_address()


class LivePlot1D(qt.QWidget):
    def __init__(self, *args, **kw):
        self._data_dict = kw.pop("data_dict")
        self._session_name = kw.pop("session_name")
        self.plot_id = None  # filled by caller
        host, port = REDIS_CACHE
        if host != "localhost":
            self.redis_cnx = redis.Redis(host=host, port=port)
        else:
            self.redis_cnx = redis.Redis(unix_socket_path=port)

        qt.QWidget.__init__(self, *args, **kw)

        self._enabled_plots = dict()
        self._curves = dict()
        self.silx_plot = silx_plot.Plot1D(self)
        self.x_axis_names = list()
        self.y_axis_names = list()
        self.legend_icon = weakref.WeakValueDictionary()

        self.axes_list_view = qt.QTreeView(self)
        self.axes_list_model = qt.QStandardItemModel(self.axes_list_view)
        self.axes_list_view.setModel(self.axes_list_model)
        self.axes_list_model.itemChanged.connect(self._axes_item_changed)

        qt.QVBoxLayout(self)
        self.layout().addWidget(self.silx_plot)
        self.layout().addWidget(self.axes_list_view)

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
        self.x_axis_names = axis_names_list
        self.axes_list_model.clear()
        self.axes_list_model.setHorizontalHeaderLabels(
            ["Counter", "X", "Y1", "Y2", "Legend", ""]
        )
        for i, axis_name in enumerate(sorted(axis_names_list)):
            item_name = qt.QStandardItem(axis_name)
            item_name.setEditable(False)

            item_select_x = qt.QStandardItem("")
            item_select_x.setEditable(False)
            item_select_x.setCheckable(True)
            if not i:
                item_select_x.setCheckState(qt.Qt.Checked)
                axis = self.silx_plot.getXAxis()
                axis.setLabel(axis_name.split(":")[-1])
            self.axes_list_model.appendRow([item_name, item_select_x])

    def set_y_axes(self, axis_names_list):
        self.y_axis_names = axis_names_list
        plot_selected = self.redis_cnx.hgetall("%s:plot_select" % self._session_name)
        self.silx_plot.clearCurves()
        for x_row in range(self.axes_list_model.rowCount()):
            x_item = self.axes_list_model.item(x_row, 1)
            if x_item.checkState() == qt.Qt.Checked:
                x_axis = self.axes_list_model.item(x_item.row()).text()
                break

        for i, axis_name in enumerate(sorted(axis_names_list)):
            try:
                y_selected_axis = {None: 0, "Y1": 1, "Y2": 2}[
                    plot_selected.get(axis_name)
                ]
            except KeyError:
                y_selected_axis = 0

            item_name = qt.QStandardItem(axis_name)
            item_name.setEditable(False)
            x_select = qt.QStandardItem("")
            x_select.setEditable(False)
            items = [item_name, x_select]

            gb = qt.QButtonGroup(self)
            for k in range(1, 3):
                item_select = qt.QStandardItem("")
                item_select.setEditable(False)
                item_select.setCheckable(True)
                items.append(item_select)
                if y_selected_axis == k:
                    item_select.setCheckState(qt.Qt.Checked)
                    legend = "%s -> %s" % (x_axis, axis_name)
                    key = self.silx_plot.addCurve([], [], legend=legend, copy=False)
                    curve = self.silx_plot.getCurve(legend)
                    curve.setYAxis("left" if k == 2 else "right")
                    curve.sigItemChanged.connect(self._refresh_legend)

            row_id = self.axes_list_model.rowCount()
            self.axes_list_model.appendRow(items)
            # legend
            legend_icon = LegendSelector.LegendIcon(self)
            qindex = self.axes_list_model.index(row_id, 4, qt.QModelIndex())
            self.axes_list_view.setIndexWidget(qindex, legend_icon)
            self.legend_icon[row_id] = legend_icon

        for i in range(5):
            self.axes_list_view.resizeColumnToContents(i)
        self._refresh_y_label()
        self._refresh_legend()

    def _axes_item_changed(self, changed_item):
        column = changed_item.column()
        row = changed_item.row()
        axis_name = self.axes_list_model.item(row).text()
        if changed_item.isCheckable():
            if column == 1:  # X
                if changed_item.checkState() == qt.Qt.Unchecked:
                    # check that an other one is checked
                    for row in range(self.axes_list_model.rowCount()):
                        item = self.axes_list_model.item(row, 1)
                        if item == changed_item:
                            continue
                        if item.checkState() == qt.Qt.Checked:
                            break
                    else:
                        changed_item.setCheckState(
                            qt.Qt.Checked
                        )  # always one checked at least
                        return
                else:
                    axis = self.silx_plot.getXAxis()
                    for row in range(self.axes_list_model.rowCount()):
                        item = self.axes_list_model.item(row, 1)
                        if item == changed_item:
                            continue
                        if item.checkState() == qt.Qt.Checked:
                            item.setCheckState(qt.Qt.Unchecked)
                    axis.setLabel(axis_name.split(":")[-1])
                    # refresh all curves
                    self.silx_plot.clearCurves()
                    for row in range(self.axes_list_model.rowCount()):
                        for item, yaxis in zip(
                            [
                                self.axes_list_model.item(row, column)
                                for column in range(2, 4)
                            ],
                            ("left", "right"),
                        ):
                            if item is not None and item.checkState() == qt.Qt.Checked:
                                y_axis_name = str(self.axes_list_model.item(row).text())
                                legend = "%s -> %s" % (axis_name, y_axis_name)
                                key = self.silx_plot.addCurve(
                                    [], [], legend=legend, copy=False
                                )
                                curve = self.silx_plot.getCurve(key)
                                curve.setYAxis(yaxis)
                                curve.sigItemChanged.connect(self._refresh_legend)
                    self.update_plots()
                    self._refresh_y_label()
                    self._refresh_legend()
            elif column == 2 or column == 3:
                for x_row in range(self.axes_list_model.rowCount()):
                    x_item = self.axes_list_model.item(x_row, 1)
                    if x_item.checkState() == qt.Qt.Checked:
                        x_axis = self.axes_list_model.item(x_item.row()).text()
                        break
                y_axis = axis_name
                legend = "%s -> %s" % (x_axis, y_axis)
                if changed_item.checkState() == qt.Qt.Checked:
                    unselect_column = 3 if column == 2 else 2
                    item = self.axes_list_model.item(row, unselect_column)
                    if item.checkState() == qt.Qt.Checked:
                        item.setCheckState(qt.Qt.Unchecked)
                    # add the curve
                    x_data, y_data = self._get_data(x_axis, y_axis)
                    existed_curve = self.silx_plot.getCurve(legend)
                    key = self.silx_plot.addCurve(
                        x_data, y_data, legend=legend, copy=False
                    )
                    curve = self.silx_plot.getCurve(key)
                    if not existed_curve:
                        curve.sigItemChanged.connect(self._refresh_legend)
                    curve.setYAxis("left" if column == 2 else "right")
                    self.redis_cnx.hset(
                        "%s:plot_select" % self._session_name,
                        y_axis,
                        "Y1" if column == 2 else "Y2",
                    )
                else:
                    self.redis_cnx.hdel("%s:plot_select" % self._session_name, y_axis)
                    self.silx_plot.removeCurve(legend)
                    color = qt.QColor.fromRgbF(0., 0., 0., 0.)
                    icon = self.legend_icon[row]
                    icon.setLineColor(color)
                    icon.setSymbolColor(color)
                    icon.update()

                self._refresh_y_label()
                self._refresh_legend()

    def _refresh_y_label(self):
        y1_label = list()
        y2_label = list()
        for row in range(self.axes_list_model.rowCount()):
            axis_item = self.axes_list_model.item(row)
            label = str(axis_item.text()).split(":")[-1]
            for column, y_list in zip(range(2, 4), [y1_label, y2_label]):
                item = self.axes_list_model.item(row, column)
                if (
                    item is not None
                    and item.isCheckable()
                    and item.checkState() == qt.Qt.Checked
                ):
                    y_list.append(label)
        y1_axis = self.silx_plot.getYAxis()
        y1_axis.setLabel("\n".join(y1_label))
        y2_axis = self.silx_plot.getYAxis(axis="right")
        y2_axis.setLabel("\n".join(y2_label))

    def _refresh_legend(self):
        x_axis = None
        for row in range(self.axes_list_model.rowCount()):
            axis_name = str(self.axes_list_model.item(row).text())
            x_item = self.axes_list_model.item(row, 1)
            if x_item.checkState() == qt.Qt.Checked:
                x_axis = axis_name
                continue
            legend = "%s -> %s" % (x_axis, axis_name)
            curve = self.silx_plot.getCurve(legend)
            if curve is None:
                continue
            icon = self.legend_icon[row]
            icon.setSymbol(curve.getSymbol())
            icon.setLineWidth(curve.getLineWidth())
            icon.setLineStyle(curve.getLineStyle())
            color = curve.getCurrentColor()
            if numpy.array(color, copy=False).ndim != 1:
                # array of colors, use transparent black
                color = 0., 0., 0., 0.
            color = colors.rgba(color)  # Make sure it is float in [0, 1]
            alpha = curve.getAlpha()
            color = qt.QColor.fromRgbF(color[0], color[1], color[2], color[3] * alpha)
            icon.setLineColor(color)
            icon.setSymbolColor(color)
            icon.update()

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
