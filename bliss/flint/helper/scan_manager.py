# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
""""
Manage scan events to feed with the application model
"""
from __future__ import annotations
from typing import Optional
from typing import List
from typing import Dict
from typing import Tuple

import sys
import warnings
import collections
import logging

import numpy
import gevent.event

from silx.gui import qt

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui.plot import Plot1D
    from silx.gui.plot import Plot2D

from ..widgets.live_plot_1d import LivePlot1D
from ..widgets.live_scatter_plot import LiveScatterPlot


_logger = logging.getLogger(__name__)


class ScanManager:
    def __init__(self, flint):
        self.flint = flint
        self.mdi_windows_dict: Dict[str, qt.QMdiSubWindow] = {}
        self._refresh_task = None
        self._last_event: Dict[
            Tuple[str, Optional[str]], Tuple[str, numpy.ndarray]
        ] = dict()

        def new_live_scan_plots():
            return {"0d": [], "1d": [], "2d": []}

        self.live_scan_plots_dict: Dict[
            str, List[qt.QWidget]
        ] = collections.defaultdict(new_live_scan_plots)
        self._end_scan_event = gevent.event.Event()

    def new_scan(self, scan_info):

        # show tab
        self.flint.parent_tab.setCurrentIndex(0)
        self.flint.parent_tab.setTabText(
            0,
            "Live scan | %s - scan number %d"
            % (scan_info["title"], scan_info["scan_nb"]),
        )

        # delete plots data
        for master, plots in self.live_scan_plots_dict.items():
            for plot_type in ("0d", "1d", "2d"):
                for plot in plots[plot_type]:
                    self.flint.data_dict.pop(plot.plot_id, None)

        old_window_titles = []
        for mdi_window in self.flint.live_scan_mdi_area.subWindowList():
            plot = mdi_window.widget()
            window_title = plot.windowTitle()
            old_window_titles.append(window_title)

        # create new windows
        flags = (
            qt.Qt.Window
            | qt.Qt.WindowMinimizeButtonHint
            | qt.Qt.WindowMaximizeButtonHint
            | qt.Qt.WindowTitleHint
        )
        window_titles = []
        for master, channels in scan_info["acquisition_chain"].items():
            scalars = channels.get("scalars", [])
            spectra = channels.get("spectra", [])
            # merge master which are spectra
            if "spectra" in channels:
                for c in channels["master"].get("spectra", []):
                    if c not in spectra:
                        spectra.append(c)
            images = channels.get("images", [])
            # merge master which are image
            if "master" in channels:
                for c in channels["master"].get("images", []):
                    if c not in images:
                        images.append(c)

            if scalars:
                window_title = "1D: " + master + " -> counters"
                window_titles.append(window_title)
                scalars_plot_win = self.mdi_windows_dict.get(window_title)
                if not scalars_plot_win:
                    scalars_plot_win = LivePlot1D(**self.flint.redis_session_info())
                    scalars_plot_win.setWindowTitle(window_title)
                    scalars_plot_win.plot_id = self.flint.create_new_id()
                    self.flint.plot_dict[scalars_plot_win.plot_id] = scalars_plot_win
                    self.live_scan_plots_dict[master]["0d"].append(scalars_plot_win)
                    self.mdi_windows_dict[
                        window_title
                    ] = self.flint.live_scan_mdi_area.addSubWindow(
                        scalars_plot_win, flags
                    )
                    scalars_plot_win.show()
                else:
                    scalars_plot_win = scalars_plot_win.widget()
                scalars_plot_win.set_x_axes(channels["master"]["scalars"])
                scalars_plot_win.set_y_axes(scalars)

                if (
                    len(channels["master"]["scalars"]) >= 2
                    and scan_info.get("data_dim", 1) == 2
                ):
                    window_title = "Scatter: " + master + " -> counters"
                    window_titles.append(window_title)
                    scatter_plot_win = self.mdi_windows_dict.get(window_title)
                    if not scatter_plot_win:
                        scatter_plot_win = LiveScatterPlot(
                            **self.flint.redis_session_info()
                        )
                        scatter_plot_win.setWindowTitle(window_title)
                        scatter_plot_win.plot_id = self.flint.create_new_id()
                        self.flint.plot_dict[
                            scatter_plot_win.plot_id
                        ] = scatter_plot_win
                        self.live_scan_plots_dict[master]["0d"].append(scatter_plot_win)
                        self.mdi_windows_dict[
                            window_title
                        ] = self.flint.live_scan_mdi_area.addSubWindow(
                            scatter_plot_win, flags
                        )
                        scatter_plot_win.show()
                    else:
                        scatter_plot_win = scatter_plot_win.widget()
                    scatter_plot_win.set_x_axes(channels["master"]["scalars"])
                    scatter_plot_win.set_z_axes(scalars)
                    scatter_plot_win.set_scan_info(
                        scan_info.get("title", ""),
                        scan_info.get("instrument", {}).get("positioners", dict()),
                    )

            for spectrum in spectra:
                window_title = "1D: " + master + " -> " + spectrum
                window_titles.append(window_title)
                spectrum_win = self.mdi_windows_dict.get(window_title)
                if not spectrum_win:
                    spectrum_win = Plot1D()
                    spectrum_win.setWindowTitle(window_title)
                    spectrum_win.plot_id = self.flint.create_new_id()
                    self.flint.plot_dict[spectrum_win.plot_id] = spectrum_win
                    self.live_scan_plots_dict[master]["1d"].append(spectrum_win)
                    self.mdi_windows_dict[
                        window_title
                    ] = self.flint.live_scan_mdi_area.addSubWindow(spectrum_win, flags)
                spectrum_win.show()

            for image in images:
                window_title = "2D: " + master + " -> " + image
                window_titles.append(window_title)
                image_win = self.mdi_windows_dict.get(image)
                if not image_win:
                    image_win = Plot2D()
                    image_win.setKeepDataAspectRatio(True)
                    image_win.getYAxis().setInverted(True)
                    image_win.getIntensityHistogramAction().setVisible(True)
                    image_win.plot_id = self.flint.create_new_id()
                    self.flint.plot_dict[image_win.plot_id] = image_win
                    self.live_scan_plots_dict[master]["2d"].append(image_win)
                    self.mdi_windows_dict[
                        image
                    ] = self.flint.live_scan_mdi_area.addSubWindow(image_win, flags)
                else:
                    if (
                        image_win.widget()
                        not in self.live_scan_plots_dict[master]["2d"]
                    ):
                        self.live_scan_plots_dict[master]["2d"].append(
                            image_win.widget()
                        )
                image_win.setWindowTitle(window_title)
                image_win.show()

        # delete unused plots and windows
        for window_title in old_window_titles:
            if window_title not in window_titles:
                # need to clean window
                plot_type, master, _, data_source = window_title.split()

                if plot_type.startswith("2D"):
                    if any([title.endswith(data_source) for title in window_titles]):
                        continue
                    else:
                        window_title = data_source

                window = self.mdi_windows_dict[window_title]
                plot = window.widget()
                del self.flint.plot_dict[plot.plot_id]

                if isinstance(plot, Plot1D):
                    self.live_scan_plots_dict[master]["1d"].remove(plot)
                elif isinstance(plot, Plot2D):
                    self.live_scan_plots_dict[master]["2d"].remove(plot)
                else:
                    self.live_scan_plots_dict[master]["0d"].remove(plot)

                del self.mdi_windows_dict[window_title]
                window.close()

        self.flint.live_scan_mdi_area.tileSubWindows()
        self._end_scan_event.clear()

    def new_scan_data(self, data_type, master_name, data):
        if data_type in ("1d", "2d"):
            key = master_name, data["channel_name"]
        else:
            key = master_name, None

        self._last_event[key] = (data_type, data)
        if self._refresh_task is None:
            self._refresh_task = gevent.spawn(self._refresh)

    def end_scan(self, scan_info):
        self._end_scan_event.set()

    def wait_end_of_scan(self):
        self._end_scan_event.wait()

    def _refresh(self):
        try:
            while self._last_event:
                local_event = self._last_event
                self._last_event = dict()
                for (master_name, _), (data_type, data) in local_event.items():
                    try:
                        self._new_scan_data(data_type, master_name, data)
                    except Exception:
                        _logger.error("Error while reaching data", exc_info=True)
        finally:
            self._refresh_task = None

    def _new_scan_data(self, data_type, master_name, data):
        if data_type == "0d":
            for plot in self.live_scan_plots_dict[master_name]["0d"]:
                plot._set_data(data["data"])
                plot.update_all()

        elif data_type == "1d":
            channel_name = data["channel_name"]
            spectrum_data = data["channel_data_node"].get(-1)
            plot = self.live_scan_plots_dict[master_name]["1d"][data["channel_index"]]
            self.flint.update_data(plot.plot_id, channel_name, spectrum_data)
            if spectrum_data.ndim == 1:
                length, = spectrum_data.shape
                x = numpy.arange(length)
                y = spectrum_data
            else:
                # assuming ndim == 2
                x = spectrum_data[0]
                y = spectrum_data[1]
            plot.addCurve(x, y, legend=channel_name)

        elif data_type == "2d":
            plot = self.live_scan_plots_dict[master_name]["2d"][data["channel_index"]]
            channel_name = data["channel_name"]
            channel_data_node = data["channel_data_node"]
            channel_data_node.from_stream = True
            image_view = channel_data_node.get(-1)
            image_data = image_view.get_image(-1)
            self.flint.update_data(plot.plot_id, channel_name, image_data)
            plot_image = plot.getImage(channel_name)  # returns last plotted image
            if plot_image is None:
                plot.addImage(image_data, legend=channel_name, copy=False)
            else:
                plot_image.setData(image_data, copy=False)
        data_event = (
            self.flint.data_event[master_name]
            .setdefault(data_type, {})
            .setdefault(data.get("channel_index", 0), gevent.event.Event())
        )
        data_event.set()
