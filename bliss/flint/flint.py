# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# Imports
import os
import sys
import types
import logging
import platform
import tempfile
import warnings
import itertools
import functools
import contextlib
import collections
import signal

import numpy
import gevent
import gevent.event

from bliss.comm import rpc
from bliss.data.scan import watch_session_scans
from bliss.config.conductor.client import get_default_connection
from bliss.config.conductor.client import (
    get_redis_connection,
    clean_all_redis_connection,
)
from bliss.flint.qgevent import set_gevent_dispatcher

from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui.plot import Plot2D
    from silx.gui import plot as silx_plot
    from silx.gui import qt
    from silx.gui.plot.tools.roi import RegionOfInterestManager
    from silx.gui.plot.tools.roi import RegionOfInterestTableWidget
    from silx.gui.plot.items.roi import RectangleROI

from .plot1d import Plot1D, LivePlot1D, LiveScatterPlot
from .interaction import PointsSelector, ShapeSelector

# Globals

pyqtRemoveInputHook()

# Logging

LOGGER = logging.getLogger()


@contextlib.contextmanager
def ignore_warnings(logger=LOGGER):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        level = logger.level
        try:
            logger.level = logging.ERROR
            yield
        finally:
            logger.level = level


# Gevent functions


@contextlib.contextmanager
def safe_rpc_server(obj):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        url = "ipc://{}".format(f.name)
        server = rpc.Server(obj)
        try:
            server.bind(url)
            task = gevent.spawn(server.run)
            yield task, url
            task.kill()
            task.join()
        finally:
            server.close()


@contextlib.contextmanager
def maintain_value(key, value):
    redis = get_redis_connection()
    redis.lpush(key, value)
    yield
    redis.delete(key)


def get_flint_key():
    return "flint:{}:{}:{}".format(platform.node(), os.environ.get("USER"), os.getpid())


def background_task(flint, stop):
    key = get_flint_key()
    with safe_rpc_server(flint) as (task, url):
        with maintain_value(key, url):
            gevent.wait([stop, task], count=1)


# Flint interface


class ROISelectionWidget(qt.QMainWindow):

    selectionFinished = qt.Signal(object)

    def __init__(self, plot, parent=None):
        qt.QMainWindow.__init__(self, parent)
        # TODO: destroy on close
        self.plot = plot
        panel = qt.QWidget()
        self.setCentralWidget(panel)

        self.roi_manager = RegionOfInterestManager(plot)
        self.roi_manager.setColor("pink")
        self.roi_manager.sigRoiAdded.connect(self.on_added)
        self.table = RegionOfInterestTableWidget()
        self.table.setRegionOfInterestManager(self.roi_manager)

        self.toolbar = qt.QToolBar()
        self.addToolBar(self.toolbar)
        rectangle_action = self.roi_manager.getInteractionModeAction(RectangleROI)
        self.toolbar.addAction(rectangle_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction("Apply", self.on_apply)

        layout = qt.QVBoxLayout(panel)
        layout.addWidget(self.table)

    def on_apply(self):
        self.selectionFinished.emit(self.roi_manager.getRois())
        self.roi_manager.clear()

    def on_added(self, roi):
        if not roi.getLabel():
            nb_rois = len(self.roi_manager.getRois())
            roi.setLabel("roi{}".format(nb_rois))

    def add_roi(self, roi):
        self.roi_manager.addRoi(roi)


class Flint:
    """Flint interface, meant to be exposed through an RPC server."""

    _id_generator = itertools.count()

    def __init__(self, parent_tab):
        self.parent_tab = parent_tab
        self.main_index = next(self._id_generator)
        self.plot_dict = {self.main_index: parent_tab}
        self.mdi_windows_dict = {}
        self.data_event = collections.defaultdict(dict)
        self.selector_dict = collections.defaultdict(list)
        self.data_dict = collections.defaultdict(dict)
        self.scans_watch_task = None
        self._session_name = None
        self._last_event = dict()
        self._refresh_task = None
        self._end_scan_event = gevent.event.Event()

        connection = get_default_connection()
        address = connection.get_redis_connection_address()
        self._qt_redis_connection = connection.create_redis_connection(address=address)

        def new_live_scan_plots():
            return {"0d": [], "1d": [], "2d": []}

        self.live_scan_plots_dict = collections.defaultdict(new_live_scan_plots)

        self.live_scan_mdi_area = self.new_tab("Live scan", qt.QMdiArea)
        self.set_title()

    def set_title(self, session_name=None):
        window = self.parent_tab.window()
        if not session_name:
            session = "no session attached."
        else:
            session = "attached to '%s`" % session_name
        title = "Flint (PID={}) - {}".format(os.getpid(), session)
        window.setWindowTitle(title)

    def get_session(self):
        return self._session_name

    def set_session(self, session_name):
        if session_name == self._session_name:
            return

        if self.scans_watch_task:
            self.scans_watch_task.kill()

        ready_event = gevent.event.Event()

        def spawn():
            task = gevent.spawn(
                watch_session_scans,
                session_name,
                self.new_scan,
                self.new_scan_child,
                self.new_scan_data,
                self.end_scan,
                ready_event=ready_event,
            )
            return task

        def respawn(old_task):
            if old_task.exception and not isinstance(
                old_task.exception, gevent.GreenletExit
            ):
                # first purge redis connection...
                # we sometime corrupt redis connection if you kill
                # the task in wrong place.
                # so close all the connection to restart for fresh.
                clean_all_redis_connection()
                t = spawn()
                t.link(respawn)

        task = spawn()
        ready_event.wait()
        task.link(respawn)

        self._session_name = session_name

        redis = get_redis_connection()
        key = get_flint_key()
        current_value = redis.lindex(key, 0).decode()
        value = session_name + " " + current_value.split()[-1]
        redis.lpush(key, value)
        redis.rpop(key)

        self.set_title(session_name)

    def new_scan(self, scan_info):
        self._end_scan_event.clear()

        # show tab
        self.parent_tab.setCurrentIndex(0)
        self.parent_tab.setTabText(
            0,
            "Live scan | %s - scan number %d"
            % (scan_info["title"], scan_info["scan_nb"]),
        )

        # delete plots data
        for master, plots in self.live_scan_plots_dict.items():
            for plot_type in ("0d", "1d", "2d"):
                for plot in plots[plot_type]:
                    self.data_dict.pop(plot.plot_id, None)

        old_window_titles = []
        for mdi_window in self.live_scan_mdi_area.subWindowList():
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
            images = channels.get("images", [])

            if scalars:
                window_title = "1D: " + master + " -> counters"
                window_titles.append(window_title)
                scalars_plot_win = self.mdi_windows_dict.get(window_title)
                if not scalars_plot_win:
                    scalars_plot_win = LivePlot1D(
                        data_dict=self.data_dict,
                        session_name=self._session_name,
                        redis_connection=self._qt_redis_connection,
                    )
                    scalars_plot_win.setWindowTitle(window_title)
                    scalars_plot_win.plot_id = next(self._id_generator)
                    self.plot_dict[scalars_plot_win.plot_id] = scalars_plot_win
                    self.live_scan_plots_dict[master]["0d"].append(scalars_plot_win)
                    self.mdi_windows_dict[
                        window_title
                    ] = self.live_scan_mdi_area.addSubWindow(scalars_plot_win, flags)
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
                            data_dict=self.data_dict,
                            session_name=self._session_name,
                            redis_connection=self._qt_redis_connection,
                        )
                        scatter_plot_win.setWindowTitle(window_title)
                        scatter_plot_win.plot_id = next(self._id_generator)
                        self.plot_dict[scatter_plot_win.plot_id] = scatter_plot_win
                        self.live_scan_plots_dict[master]["0d"].append(scatter_plot_win)
                        self.mdi_windows_dict[
                            window_title
                        ] = self.live_scan_mdi_area.addSubWindow(
                            scatter_plot_win, flags
                        )
                        scatter_plot_win.show()
                    else:
                        scatter_plot_win = scatter_plot_win.widget()
                    scatter_plot_win.set_x_axes(channels["master"]["scalars"])
                    scatter_plot_win.set_z_axes(scalars)
                    scatter_plot_win.set_scan_info(
                        scan_info.get("title", ""), scan_info.get("positioners", dict())
                    )

            for spectrum in spectra:
                window_title = "1D: " + master + " -> " + spectrum
                window_titles.append(window_title)
                spectrum_win = self.mdi_windows_dict.get(window_title)
                if not spectrum_win:
                    spectrum_win = Plot1D()
                    spectrum_win.setWindowTitle(window_title)
                    spectrum_win.plot_id = next(self._id_generator)
                    self.plot_dict[spectrum_win.plot_id] = spectrum_win
                    self.live_scan_plots_dict[master]["1d"].append(spectrum_win)
                    self.mdi_windows_dict[
                        window_title
                    ] = self.live_scan_mdi_area.addSubWindow(spectrum_win, flags)
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
                    image_win.plot_id = next(self._id_generator)
                    self.plot_dict[image_win.plot_id] = image_win
                    self.live_scan_plots_dict[master]["2d"].append(image_win)
                    self.mdi_windows_dict[image] = self.live_scan_mdi_area.addSubWindow(
                        image_win, flags
                    )
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
                del self.plot_dict[plot.plot_id]

                if isinstance(plot, Plot1D):
                    self.live_scan_plots_dict[master]["1d"].remove(plot)
                elif isinstance(plot, Plot2D):
                    self.live_scan_plots_dict[master]["2d"].remove(plot)
                else:
                    self.live_scan_plots_dict[master]["0d"].remove(plot)

                del self.mdi_windows_dict[window_title]
                window.close()

        self.live_scan_mdi_area.tileSubWindows()

    def wait_data(self, master, plot_type, index):
        ev = (
            self.data_event[master]
            .setdefault(plot_type, {})
            .setdefault(index, gevent.event.Event())
        )
        ev.wait(timeout=3)

    def get_live_scan_plot(self, master, plot_type, index):
        return self.live_scan_plots_dict[master][plot_type][index].plot_id

    def new_scan_child(self, scan_info, data_channel):
        pass

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
                    last_data = data["data"]
                    if data_type in ("1d", "2d"):
                        if data_type == "2d":
                            last_data.from_stream = True
                        try:
                            last_data = last_data[-1]
                        except IndexError:
                            continue
                    else:
                        data["channel_index"] = 0
                    try:
                        self._new_scan_data(data_type, master_name, data, last_data)
                    except:
                        sys.excepthook(*sys.exc_info())
        finally:
            self._refresh_task = None

    def _new_scan_data(self, data_type, master_name, data, last_data):
        if data_type == "0d":
            for plot in self.live_scan_plots_dict[master_name]["0d"]:
                for channel_name, channel_data in last_data.items():
                    self.update_data(plot.plot_id, channel_name, channel_data)
                plot.update_all()
        elif data_type == "1d":
            spectrum_data = last_data
            channel_name = data["channel_name"]
            plot = self.live_scan_plots_dict[master_name]["1d"][data["channel_index"]]
            self.update_data(plot.plot_id, channel_name, spectrum_data)
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
            image_data = last_data
            self.update_data(plot.plot_id, channel_name, image_data)
            plot_image = plot.getImage(channel_name)  # returns last plotted image
            if plot_image is None:
                plot.addImage(image_data, legend=channel_name, copy=False)
            else:
                plot_image.setData(image_data, copy=False)
        data_event = (
            self.data_event[master_name]
            .setdefault(data_type, {})
            .setdefault(data["channel_index"], gevent.event.Event())
        )
        data_event.set()

    def new_tab(self, label, widget=qt.QWidget):
        widget = widget()
        self.parent_tab.addTab(widget, label)
        return widget

    def run_method(self, key, method, args, kwargs):
        plot = self.plot_dict[key]
        method = getattr(plot, method)
        return method(*args, **kwargs)

    # Plot management

    def add_plot(self, cls_name, name=None):
        plot_id = next(self._id_generator)
        if not name:
            name = "Plot %d" % plot_id
        new_tab_widget = self.new_tab(name)
        qt.QVBoxLayout(new_tab_widget)
        cls = getattr(silx_plot, cls_name)
        plot = cls(new_tab_widget)
        self.plot_dict[plot_id] = plot
        new_tab_widget.layout().addWidget(plot)
        plot.show()
        return plot_id

    def get_plot_name(self, plot_id):
        parent = self.plot_dict[plot_id].parent()
        if isinstance(parent, qt.QMdiArea):
            label = parent.windowTitle()
        else:
            index = self.parent_tab.indexOf(parent)
            label = self.parent_tab.tabText(index)
        return label

    def remove_plot(self, plot_id):
        plot = self.plot_dict.pop(plot_id)
        parent = plot.parent()
        index = self.parent_tab.indexOf(parent)
        self.parent_tab.removeTab(index)
        plot.close()

    def get_interface(self, plot_id):
        plot = self.plot_dict[plot_id]
        names = dir(plot)
        with ignore_warnings():
            return [
                name
                for name in names
                if not name.startswith("_")
                if callable(getattr(plot, name))
            ]

    # Data management

    def update_data(self, plot_id, field, data):
        self.data_dict[plot_id][field] = data

    def remove_data(self, plot_id, field):
        del self.data_dict[plot_id][field]

    def get_data(self, plot_id, field=None):
        if field is None:
            return self.data_dict[plot_id]
        else:
            return self.data_dict[plot_id].get(field, [])

    def select_data(self, plot_id, method, names, kwargs):
        plot = self.plot_dict[plot_id]
        # Hackish legend handling
        if "legend" not in kwargs and method.startswith("add"):
            kwargs["legend"] = " -> ".join(names)
        # Get the data to plot
        args = tuple(self.data_dict[plot_id][name] for name in names)
        method = getattr(plot, method)
        # Plot
        method(*args, **kwargs)

    def deselect_data(self, plot_id, names):
        plot = self.plot_dict[plot_id]
        legend = " -> ".join(names)
        plot.remove(legend)

    def clear_data(self, plot_id):
        del self.data_dict[plot_id]
        plot = self.plot_dict[plot_id]
        plot.clear()

    # User interaction

    def select_shapes(self, plot_id, initial_shapes=(), timeout=None):
        plot = self.plot_dict[plot_id]
        dock = self._create_roi_dock_widget(plot, initial_shapes)
        roi_widget = dock.widget()
        done_event = gevent.event.AsyncResult()

        roi_widget.selectionFinished.connect(
            functools.partial(self._selectionFinished, done_event=done_event)
        )

        try:
            return done_event.get(timeout=timeout)
        finally:
            plot.removeDockWidget(dock)

    def _selectionFinished(self, selections, done_event=None):
        shapes = []
        try:
            shapes = [
                dict(
                    origin=select.getOrigin(),
                    size=select.getSize(),
                    label=select.getLabel(),
                    kind=select._getKind(),
                )
                for select in selections
            ]
        finally:
            done_event.set_result(shapes)

    def _create_roi_dock_widget(self, plot, initial_shapes):
        roi_widget = ROISelectionWidget(plot)
        dock = qt.QDockWidget("ROI selection")
        dock.setWidget(roi_widget)
        plot.addTabbedDockWidget(dock)
        for shape in initial_shapes:
            kind = shape["kind"]
            if kind == "Rectangle":
                roi = RectangleROI()
                roi.setGeometry(origin=shape["origin"], size=shape["size"])
                roi.setLabel(shape["label"])
                roi_widget.add_roi(roi)
            else:
                raise ValueError("Unknown shape of type {}".format(kind))
        dock.show()
        return dock

    def _selection(self, plot_id, cls, *args):
        # Instanciate selector
        plot = self.plot_dict[plot_id]
        selector = qt_safe(cls)(plot)
        # Save it for future cleanup
        self.selector_dict[plot_id].append(selector)
        # Run the selection
        queue = QtSignalQueue(selector.selectionFinished)
        qt_safe(selector.start)(*args)
        try:
            positions, = queue.get()
        finally:
            queue.disconnect()
        return positions

    def select_points(self, plot_id, nb):
        return self._selection(plot_id, PointsSelector, nb)

    def select_shape(self, plot_id, shape):
        return self._selection(plot_id, ShapeSelector, shape)

    def clear_selections(self, plot_id):
        for selector in self.selector_dict.pop(plot_id):
            selector.reset()


class QtLogHandler(logging.Handler):
    def __init__(self, log_widget):
        logging.Handler.__init__(self)

        self.log_widget = log_widget

    def emit(self, record):
        record = self.format(record)
        self.log_widget.appendPlainText(record)


# Main execution


def main():
    set_gevent_dispatcher()

    qapp = qt.QApplication(sys.argv)
    qapp.setApplicationName("flint")
    qapp.setOrganizationName("ESRF")
    qapp.setOrganizationDomain("esrf.eu")

    win = qt.QMainWindow()
    central_widget = qt.QWidget(win)
    tabs = qt.QTabWidget(central_widget)
    win.setCentralWidget(tabs)
    log_window = qt.QWidget()
    log_widget = qt.QPlainTextEdit()
    qt.QVBoxLayout(log_window)
    log_window.layout().addWidget(log_widget)
    log_window.setAttribute(qt.Qt.WA_QuitOnClose, False)
    log_widget.setReadOnly(True)
    log_window.setWindowTitle("Log messages")
    exitAction = qt.QAction("&Exit", win)
    exitAction.setShortcut("Ctrl+Q")
    exitAction.setStatusTip("Exit flint")
    exitAction.triggered.connect(qapp.quit)
    showLogAction = qt.QAction("Show &log", win)
    showLogAction.setShortcut("Ctrl+L")
    showLogAction.setStatusTip("Show log window")
    showLogAction.triggered.connect(log_window.show)
    menubar = win.menuBar()
    fileMenu = menubar.addMenu("&File")
    fileMenu.addAction(exitAction)
    windowMenu = menubar.addMenu("&Windows")
    windowMenu.addAction(showLogAction)

    settings = qt.QSettings()

    def save_window_settings():
        settings.setValue("size", win.size())
        settings.setValue("pos", win.pos())
        settings.sync()

    qapp.aboutToQuit.connect(save_window_settings)

    # resize window to 70% of available screen space, if no settings
    pos = qt.QDesktopWidget().availableGeometry(win).size() * 0.7
    w = pos.width()
    h = pos.height()
    win.resize(settings.value("size", qt.QSize(w, h)))
    win.move(settings.value("pos", qt.QPoint(3 * w / 14.0, 3 * h / 14.0)))

    handler = QtLogHandler(log_widget)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s: %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.level = logging.INFO

    def handle_exception(exc_type, exc_value, exc_traceback):
        LOGGER.critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception

    # set up CTRL-C signal handler, that exits gracefully
    def sigint_handler(*args):
        qapp.quit()

    signal.signal(signal.SIGINT, sigint_handler)
    # enable periodic execution of Qt's loop,
    # this is to react on SIGINT
    # (from stackoverflow answer: https://stackoverflow.com/questions/4938723)
    timer = qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    stop = gevent.event.AsyncResult()
    flint = Flint(tabs)

    thread = gevent.spawn(background_task, flint, stop)

    single_shot = qt.QTimer()
    single_shot.setSingleShot(True)
    single_shot.timeout.connect(win.show)
    single_shot.start(0)

    try:
        sys.exit(qapp.exec_())
    finally:
        stop.set_result(True)
        thread.join()


if __name__ == "__main__":
    main()
