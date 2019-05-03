# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import warnings
import numpy
import re


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import plot as silx_plot
    from silx.gui import qt, colors
    from silx.gui.plot import LegendSelector

Plot1D = silx_plot.Plot1D


class LivePlot1D(qt.QWidget):
    def __init__(self, *args, **kw):
        self._data_dict = kw.pop("data_dict")
        self._session_name = kw.pop("session_name")
        self.plot_id = None  # filled by caller
        self.redis_cnx = kw.pop("redis_connection")

        qt.QWidget.__init__(self, *args, **kw)

        self._enabled_plots = dict()
        self._curves = dict()
        self.silx_plot = silx_plot.Plot1D(self)
        self.x_axis_names = list()
        self.y_axis_names = list()

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
        for i, axis_name in enumerate(axis_names_list):
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
        raw_plot_selected = self.redis_cnx.hgetall(
            "%s:plot_select" % self._session_name
        )
        plot_selected = {
            key.decode(): value.decode() for key, value in raw_plot_selected.items()
        }
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

            for k in range(1, 3):
                item_select = qt.QStandardItem("")
                item_select.setEditable(False)
                item_select.setCheckable(True)
                items.append(item_select)
                if y_selected_axis == k:
                    item_select.setCheckState(qt.Qt.Checked)
                    legend = "%s -> %s" % (x_axis, axis_name)
                    self.silx_plot.addCurve([], [], legend=legend, copy=False)
                    curve = self.silx_plot.getCurve(legend)
                    curve.setYAxis("right" if k == 2 else "left")
                    curve.sigItemChanged.connect(self._refresh_legend)

            row_id = self.axes_list_model.rowCount()
            self.axes_list_model.appendRow(items)
            # legend
            qindex = self.axes_list_model.index(row_id, 4, qt.QModelIndex())
            self.axes_list_view.setIndexWidget(
                qindex, LegendSelector.LegendIcon(self.axes_list_view)
            )

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

                    qindex = self.axes_list_model.index(row, 4, qt.QModelIndex())
                    icon = self.axes_list_view.indexWidget(qindex)
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
            for column, y_list in zip(list(range(2, 4)), [y1_label, y2_label]):
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
            qindex = self.axes_list_model.index(row, 4, qt.QModelIndex())
            icon = self.axes_list_view.indexWidget(qindex)
            if icon is not None:
                icon.setSymbol(curve.getSymbol())
                icon.setLineWidth(curve.getLineWidth())
                icon.setLineStyle(curve.getLineStyle())
                color = curve.getCurrentColor()
                if numpy.array(color, copy=False).ndim != 1:
                    # array of colors, use transparent black
                    color = 0., 0., 0., 0.
                color = colors.rgba(color)  # Make sure it is float in [0, 1]
                alpha = curve.getAlpha()
                color = qt.QColor.fromRgbF(
                    color[0], color[1], color[2], color[3] * alpha
                )
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
        for axis_names, data_len in self._enabled_plots.items():
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
        self._session_name = kw.pop("session_name")
        self.plot_id = None  # filled by caller
        self.redis_cnx = kw.pop("redis_connection")

        qt.QWidget.__init__(self, *args, **kw)

        self.silx_plot = silx_plot.ScatterView(self)

        self.axes_list_view = qt.QTreeView(self)
        self.axes_list_model = qt.QStandardItemModel(self.axes_list_view)
        self.axes_list_view.setModel(self.axes_list_model)
        self.axes_list_model.itemChanged.connect(self._axes_item_changed)

        qt.QVBoxLayout(self)
        self.layout().addWidget(self.silx_plot)
        self.layout().addWidget(self.axes_list_view)

        self.motor_2_ranges = dict()

    def __getattr__(self, attr):
        """Delegate to silx plot widget"""
        if attr.startswith("__"):
            raise AttributeError
        return getattr(self.silx_plot, attr)

    def set_x_axes(self, axis_names_list):
        self.axes_list_model.clear()
        self.axes_list_model.setHorizontalHeaderLabels(["Counter", "X", "Y", "Z", ""])
        self.silx_plot.setData([], [], [], copy=False)

        for i, axis_name in enumerate(axis_names_list):
            item_name = qt.QStandardItem(axis_name)
            item_name.setEditable(False)

            item_select_x = qt.QStandardItem("")
            item_select_x.setEditable(False)
            item_select_x.setCheckable(True)

            item_select_y = qt.QStandardItem("")
            item_select_y.setEditable(False)
            item_select_y.setCheckable(True)
            if i == 0:
                item_select_x.setCheckState(qt.Qt.Checked)
            elif i == 1:
                item_select_y.setCheckState(qt.Qt.Checked)
            self.axes_list_model.appendRow([item_name, item_select_x, item_select_y])

    def set_z_axes(self, axis_names_list):
        raw_scatter_selected = self.redis_cnx.hgetall(
            "%s:scatter_select" % self._session_name
        )
        scatter_selected = {
            key.decode(): value.decode() for key, value in raw_scatter_selected.items()
        }
        already_select_one = False
        for axis_name in sorted(axis_names_list):
            item_name = qt.QStandardItem(axis_name)
            item_name.setEditable(False)

            items = [item_name]
            for i in range(2):
                item = qt.QStandardItem("")
                item.setEditable(False)
                items.append(item)
            item_select_z = qt.QStandardItem("")
            item_select_z.setEditable(False)
            item_select_z.setCheckable(True)
            if already_select_one is False and scatter_selected.get(axis_name):
                already_select_one = True
                item_select_z.setCheckState(qt.Qt.Checked)
            items.append(item_select_z)

            self.axes_list_model.appendRow(items)

        for i in range(4):
            self.axes_list_view.resizeColumnToContents(i)

    def set_scan_info(self, title, positioners):
        """
        In this method, we will guess motors position ranges
        """
        scan_name = re.compile(r"^(d|a?)\w+?\s+")
        mot_name_params = re.compile(
            "(\w+)\s+(-?\d+\.\d+|-?\d+)\s+(-?\d+\.\d+|-?\d+)\s(\d+)"
        )
        self.motor_2_ranges = dict()

        m = scan_name.match(title)
        if m is not None:
            differential = m.group(1) == "d"
            for (
                motor_name,
                start_position,
                stop_position,
                nb_points,
            ) in mot_name_params.findall(title):
                if differential:
                    current_pos = positioners.get(motor_name)
                    if current_pos is None:
                        continue
                    start_position = float(start_position) + current_pos
                    stop_position = float(stop_position) + current_pos
                self.motor_2_ranges[motor_name] = [
                    float(x) for x in (start_position, stop_position)
                ]
        self.update_range()

    def update_plots(self):
        axes = self._get_selected_axes()
        x_axis = axes.get("x_axis")
        y_axis = axes.get("y_axis")
        z_axis = axes.get("z_axis")
        if x_axis and y_axis and z_axis:
            data = self._data_dict[self.plot_id]
            x_data = data.get(x_axis)
            y_data = data.get(y_axis)
            z_data = data.get(z_axis)
            mlen = min((len(x_data), len(y_data), len(z_data)))
            self.silx_plot.setData(
                x_data[:mlen], y_data[:mlen], z_data[:mlen], copy=False
            )

    def update_range(self):
        axes = self._get_selected_axes()
        x_axis = axes.get("x_axis", "").split(":")[-1]
        x_ranges = self.motor_2_ranges.get(x_axis)
        if x_ranges is not None:
            axis = self.silx_plot.getXAxis()
            axis.setLimits(*x_ranges)

        y_axis = axes.get("y_axis", "").split(":")[-1]
        y_ranges = self.motor_2_ranges.get(y_axis)
        if y_ranges is not None:
            axis = self.silx_plot.getYAxis()
            axis.setLimits(*y_ranges)

    def update_all(self):
        self.update_plots()

    def _get_selected_axes(self):
        axes = dict()
        for row in range(self.axes_list_model.rowCount()):
            for column, axis_key in ((1, "x_axis"), (2, "y_axis"), (3, "z_axis")):
                item = self.axes_list_model.item(row, column)
                if item is not None and item.checkState() == qt.Qt.Checked:
                    axes[axis_key] = self.axes_list_model.item(row).text()
        return axes

    def _axes_item_changed(self, changed_item):
        column = changed_item.column()
        row = changed_item.row()
        axis_name = self.axes_list_model.item(row).text()
        if changed_item.isCheckable():
            if column == 1 or column == 2:
                if changed_item.checkState() == qt.Qt.Unchecked:
                    # check that an other one is checked
                    for row in range(self.axes_list_model.rowCount()):
                        item = self.axes_list_model.item(row, column)
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
                    for row in range(self.axes_list_model.rowCount()):
                        item = self.axes_list_model.item(row, column)
                        if item == changed_item:
                            continue
                        if item.checkState() == qt.Qt.Checked:
                            item.setCheckState(qt.Qt.Unchecked)
                            other_item = self.axes_list_model.item(
                                row, 1 if column == 2 else 2
                            )
                            other_item.setCheckState(qt.Qt.Checked)
            elif column == 3:
                if changed_item.checkState() == qt.Qt.Checked:
                    self.redis_cnx.hset(
                        "%s:scatter_select" % self._session_name, axis_name, 1
                    )
                    for row in range(self.axes_list_model.rowCount()):
                        item = self.axes_list_model.item(row, column)
                        if item == changed_item or item is None:
                            continue
                        if item.checkState() == qt.Qt.Checked:
                            item_name = self.axes_list_model.item(row).text()
                            self.redis_cnx.hdel(
                                "%s:scatter_select" % self._session_name, item_name
                            )
                            item.setCheckState(qt.Qt.Unchecked)
                else:
                    self.redis_cnx.hdel(
                        "%s:scatter_select" % self._session_name, axis_name
                    )

        self.update_plots()
        if column == 1 or column == 2:  # X or Y
            self.update_range()
