# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import logging
import platform
import tempfile
import warnings
import itertools
import functools
import contextlib
import collections
import signal

import gevent.event
from argparse import ArgumentParser

from bliss.comm import rpc
from bliss.data.scan import watch_session_scans
from bliss.config.conductor.client import get_default_connection
from bliss.config.conductor.client import (
    get_redis_connection,
    clean_all_redis_connection,
)
import bliss.flint.resources

try:
    from bliss.flint import poll_patch
except ImportError:
    poll_patch = None

from PyQt5.QtCore import pyqtRemoveInputHook

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import silx
    from silx.gui import qt
    from silx.gui import plot as silx_plot
    from silx.gui.plot.items.roi import RectangleROI

import bliss.release
from bliss.flint.helper.manager import ManageMainBehaviours
from bliss.flint.interaction import PointsSelector, ShapeSelector
from bliss.flint.widgets.roi_selection_widget import RoiSelectionWidget
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.widgets.property_widget import MainPropertyWidget
from bliss.flint.widgets.log_widget import LogWidget
from bliss.flint.helper import scan_manager
from bliss.flint.model import flint_model

# Globals

# FIXME is it really needed to call it outside the main function?
pyqtRemoveInputHook()

# Logging

ROOT_LOGGER = logging.getLogger()


@contextlib.contextmanager
def ignore_warnings(logger=ROOT_LOGGER):
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


class Flint:
    """Flint interface, meant to be exposed through an RPC server."""

    # FIXME: Everything relative to GUI should be removed in order to only provide
    # RPC functions

    _id_generator = itertools.count()

    def __init__(self, mainwin, parent_tab):
        self.mainwin = mainwin
        self.parent_tab = parent_tab
        self.main_index = self.create_new_id()
        self.plot_dict = {self.main_index: parent_tab}
        self.data_event = collections.defaultdict(dict)
        self.selector_dict = collections.defaultdict(list)
        self.data_dict = collections.defaultdict(dict)
        self.scans_watch_task = None
        self._session_name = None

        flintModel = self.__create_flint_model()
        self.__flintModel = flintModel

        workspace = self.__create_default_workspace()
        flintModel.setWorkspace(workspace)
        self.__scanManager = scan_manager.ScanManager(self)

        connection = get_default_connection()
        address = connection.get_redis_connection_address()
        self._qt_redis_connection = connection.create_redis_connection(address=address)
        self.set_title()

    def get_scan_manager(self):
        return self.__scanManager

    def __create_flint_model(self):
        window = self.new_tab("Live scan", qt.QMainWindow)
        window.setObjectName("scan-window")
        window.setDockNestingEnabled(True)
        window.setDockOptions(
            window.dockOptions()
            | qt.QMainWindow.AllowNestedDocks
            | qt.QMainWindow.AllowTabbedDocks
            | qt.QMainWindow.GroupedDragging
            | qt.QMainWindow.AnimatedDocks
            # | qt.QMainWindow.VerticalTabs
        )

        window.setVisible(True)

        flintModel = flint_model.FlintState()
        flintModel.setWindow(window)

        manager = ManageMainBehaviours(flintModel)
        manager.setFlintModel(flintModel)
        self.__manager = manager

        propertyWidget = MainPropertyWidget(window)
        propertyWidget.setFeatures(
            propertyWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )
        flintModel.setPropertyWidget(propertyWidget)
        window.addDockWidget(qt.Qt.LeftDockWidgetArea, propertyWidget)
        return flintModel

    def _manager(self) -> ManageMainBehaviours:
        return self.__manager

    def __create_default_workspace(self):
        # FIXME: Here we can feed the workspace with something persistent
        flintModel = self.get_flint_model()
        window = flintModel.window()

        workspace = flint_model.Workspace()
        curvePlotWidget = CurvePlotWidget(parent=window)
        curvePlotWidget.setFlintModel(flintModel)
        curvePlotWidget.setObjectName("dock1")
        curvePlotWidget.setWindowTitle("Plot1")
        curvePlotWidget.setFeatures(
            curvePlotWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )

        workspace.addWidget(curvePlotWidget)
        window.addDockWidget(qt.Qt.RightDockWidgetArea, curvePlotWidget)
        return workspace

    def get_flint_model(self) -> flint_model.FlintState:
        return self.__flintModel

    def create_new_id(self):
        return next(self._id_generator)

    def redis_session_info(self):
        return dict(
            session_name=self._session_name, redis_connection=self._qt_redis_connection
        )

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

    def _spawn_scans_session_watch(self, session_name, clean_redis=False):
        # FIXME: It could be mostly moved into scan_manager
        if clean_redis:
            clean_all_redis_connection()

        ready_event = gevent.event.Event()

        task = gevent.spawn(
            watch_session_scans,
            session_name,
            self.__scanManager.new_scan,
            self.__scanManager.new_scan_child,
            self.__scanManager.new_scan_data,
            self.__scanManager.end_scan,
            ready_event=ready_event,
        )

        task.link_exception(
            functools.partial(
                self._spawn_scans_session_watch, session_name, clean_redis=True
            )
        )

        self.scans_watch_task = task

        ready_event.wait()

        return task

    def set_session(self, session_name):
        if session_name == self._session_name:
            return

        if self.scans_watch_task:
            self.scans_watch_task.kill()

        self._spawn_scans_session_watch(session_name)
        self._session_name = session_name

        redis = get_redis_connection()
        key = get_flint_key()
        current_value = redis.lindex(key, 0).decode()
        value = session_name + " " + current_value.split()[-1]
        redis.lpush(key, value)
        redis.rpop(key)

        self.set_title(session_name)

    def wait_data(self, master, plot_type, index):
        ev = (
            self.data_event[master]
            .setdefault(plot_type, {})
            .setdefault(index, gevent.event.Event())
        )
        ev.wait(timeout=3)

    def get_live_scan_plot(self, master, plot_type, index):
        # FIXME: It is broken and should not be used
        raise Exception("get_live_scan_plot API is not available")

    def wait_end_of_scan(self):
        self.__scanManager.wait_end_of_scan()

    def new_tab(self, label, widget=qt.QWidget):
        # FIXME: The parent have to be set
        # FIXME: Rename the argument to widgetClass
        widget = widget()
        self.parent_tab.addTab(widget, label)
        return widget

    def run_method(self, key, method, args, kwargs):
        plot = self.plot_dict[key]
        method = getattr(plot, method)
        return method(*args, **kwargs)

    # Plot management

    def add_plot(self, cls_name, name=None):
        plot_id = self.create_new_id()
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

    def set_plot_dpi(self, plot_id, dpi):
        """Allow to custom the DPI of the plot

        FIXME: It have to be moved to user preferences
        """
        try:
            self.plot_dict[plot_id]._backend.fig.set_dpi(dpi)
        except Exception:
            # Prevent access to private _backend object
            pass

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
        roi_widget = RoiSelectionWidget(plot)
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
        selector = cls(plot)
        # Save it for future cleanup
        self.selector_dict[plot_id].append(selector)
        # Run the selection
        queue = gevent.queue.Queue()
        selector.selectionFinished.connect(queue.put)
        selector.start(*args)
        positions = queue.get()
        return positions

    def select_points(self, plot_id, nb):
        return self._selection(plot_id, PointsSelector, nb)

    def select_shape(self, plot_id, shape):
        return self._selection(plot_id, ShapeSelector, shape)

    def clear_selections(self, plot_id):
        for selector in self.selector_dict.pop(plot_id):
            selector.reset()


# Main execution


def create_flint(settings):
    """"
    Create Flint class and main windows without interaction with the
    environment.
    """
    win = qt.QMainWindow()
    win.setAttribute(qt.Qt.WA_QuitOnClose, True)

    central_widget = qt.QWidget(win)
    tabs = qt.QTabWidget(central_widget)
    win.setCentralWidget(tabs)
    log_window = qt.QDialog(win)
    log_widget = LogWidget(log_window)
    qt.QVBoxLayout(log_window)
    log_window.layout().addWidget(log_widget)
    log_window.setAttribute(qt.Qt.WA_QuitOnClose, False)
    log_window.setWindowTitle("Log messages")
    exitAction = qt.QAction("&Exit", win)
    exitAction.setShortcut("Ctrl+Q")
    exitAction.setStatusTip("Exit flint")
    exitAction.triggered.connect(win.close)
    showLogAction = qt.QAction("Show &log", win)
    showLogAction.setShortcut("Ctrl+L")
    showLogAction.setStatusTip("Show log window")

    def showLog():
        log_window.show()

    showLogAction.triggered.connect(showLog)
    menubar = win.menuBar()
    fileMenu = menubar.addMenu("&File")
    fileMenu.addAction(exitAction)
    windowMenu = menubar.addMenu("&Windows")
    windowMenu.addAction(showLogAction)

    def about():
        from .widgets.about import About

        About.about(win, "Flint")

    action = qt.QAction("&About", win)
    action.setStatusTip("Show the application's About box")
    action.triggered.connect(about)
    windowMenu = menubar.addMenu("&Help")
    windowMenu.addAction(action)

    log_widget.connect_logger(ROOT_LOGGER)

    flint = Flint(win, tabs)

    # resize window to 70% of available screen space, if no settings
    pos = qt.QDesktopWidget().availableGeometry(win).size() * 0.7
    w = pos.width()
    h = pos.height()
    win.resize(settings.value("size", qt.QSize(w, h)))
    win.move(settings.value("pos", qt.QPoint(3 * w / 14.0, 3 * h / 14.0)))

    return flint


def configure_parser_arguments(parser: ArgumentParser):
    version = "flint - bliss %s" % (bliss.release.short_version)
    parser.add_argument("-V", "--version", action="version", version=version)
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Set logging system in debug mode",
    )
    parser.add_argument(
        "--opengl",
        "--gl",
        dest="opengl",
        action="store_true",
        default=False,
        help="Enable OpenGL rendering (else matplotlib is used)",
    )
    parser.add_argument(
        "--enable-simulator",
        dest="simulator",
        action="store_true",
        default=False,
        help="Enable scan simulation panel",
    )


def parse_options():
    """
    Returns parsed command line argument as an `options` object.

    :raises ExitException: In case of the use of `--help` in the comman line
    """
    parser = ArgumentParser()
    configure_parser_arguments(parser)
    options = parser.parse_args()
    return options


def main():
    # patch system poll
    need_gevent_loop = True  # not poll_patch.init(1) if poll_patch else True

    logging.basicConfig(level=logging.INFO)
    ROOT_LOGGER.level = logging.INFO

    options = parse_options()
    if options.debug:
        logging.root.setLevel(logging.DEBUG)

    qapp = qt.QApplication(sys.argv)
    qapp.setApplicationName("flint")
    qapp.setOrganizationName("ESRF")
    qapp.setOrganizationDomain("esrf.eu")

    if options.opengl:
        silx.config.DEFAULT_PLOT_BACKEND = "opengl"

    bliss.flint.resources.silx_integration()

    settings = qt.QSettings()
    flint = create_flint(settings)

    def save_window_settings():
        settings.setValue("size", flint.mainwin.size())
        settings.setValue("pos", flint.mainwin.pos())
        settings.sync()

    qapp.aboutToQuit.connect(save_window_settings)

    if options.simulator:
        from bliss.flint.simulator.acquisition import AcquisitionSimulator
        from bliss.flint.simulator.simulator_widget import SimulatorWidget

        display = SimulatorWidget(flint.mainwin)
        simulator = AcquisitionSimulator(display)
        scanManager = flint.get_scan_manager()
        simulator.setScanManager(scanManager)
        display.setSimulator(simulator)
        display.show()

    def handle_exception(exc_type, exc_value, exc_traceback):
        ROOT_LOGGER.critical(
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

    if need_gevent_loop:
        timer2 = qt.QTimer()
        timer2.start(10)
        timer2.timeout.connect(lambda: gevent.sleep(0.01))
        ROOT_LOGGER.info("Gevent based on QtTimer")
    else:
        ROOT_LOGGER.info("Gevent use poll patched")

    stop = gevent.event.AsyncResult()
    thread = gevent.spawn(background_task, flint, stop)

    # FIXME: why using a timer?
    single_shot = qt.QTimer()
    single_shot.setSingleShot(True)
    single_shot.timeout.connect(flint.mainwin.show)
    single_shot.start(0)

    try:
        sys.exit(qapp.exec_())
    finally:
        stop.set_result(True)
        thread.join()


if __name__ == "__main__":
    main()
