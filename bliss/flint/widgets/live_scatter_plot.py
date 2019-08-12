# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import warnings
import re


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import plot as silx_plot
    from silx.gui import qt


class LiveScatterPlot(qt.QWidget):
    def __init__(self, parent=None, session_name=None, redis_connection=None):
        self._session_name = session_name
        # FIXME: Better to use a property
        self.plot_id = None  # filled by caller
        self.redis_cnx = redis_connection

        qt.QWidget.__init__(self, parent=parent)

        self.silx_plot = silx_plot.ScatterView(self)

        self.axes_list_view = qt.QTreeView(self)
        self.axes_list_model = qt.QStandardItemModel(self.axes_list_view)
        self.axes_list_view.setModel(self.axes_list_model)
        self.axes_list_model.itemChanged.connect(self._axes_item_changed)

        qt.QVBoxLayout(self)
        self.layout().addWidget(self.silx_plot)
        self.layout().addWidget(self.axes_list_view)

        self.motor_2_ranges = dict()
        self._data = dict()

    def _set_data(self, data):
        self._data = data

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
            r"(\w+)\s+(-?\d+\.\d+|-?\d+)\s+(-?\d+\.\d+|-?\d+)\s(\d+)"
        )
        self.motor_2_ranges = dict()

        m = scan_name.match(title)
        if m is not None:
            differential = m.group(1) == "d"
            for (
                motor_name,
                start_position,
                stop_position,
                _nb_points,
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
            data = self._data
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
