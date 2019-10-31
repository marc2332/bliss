# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Dict

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

try:
    from bliss.flint import poll_patch
except ImportError:
    poll_patch = None


# Enforce loading of PyQt5
# In case silx/matplotlib tries to import PySide, PyQt4...
import PyQt5.QtCore

with warnings.catch_warnings():
    # Avoid warning when silx will be loaded
    warnings.simplefilter("ignore")
    try:
        import h5py
    except ImportError:
        pass

import silx
from silx.gui import qt
from silx.gui import plot as silx_plot
from silx.gui.plot.items.roi import RectangleROI

import bliss.flint.resources
from bliss.flint.interaction import PointsSelector, ShapeSelector
from bliss.flint.widgets.roi_selection_widget import RoiSelectionWidget
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.widgets.property_widget import MainPropertyWidget
from bliss.flint.widgets.scan_status import ScanStatus
from bliss.flint.widgets.log_widget import LogWidget
from bliss.flint.helper.manager import ManageMainBehaviours
from bliss.flint.helper import scan_manager
from bliss.flint.helper import model_helper
from bliss.flint.model import plot_item_model
from bliss.flint.model import flint_model
from bliss.flint import config

ROOT_LOGGER = logging.getLogger()
"""Application logger"""


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
        except Exception:
            ROOT_LOGGER.error(f"Exception while serving {url}", exc_info=True)
            raise
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


class FlintServer:
    def __init__(self, flintApi):
        self.stop = gevent.event.AsyncResult()
        self.thread = gevent.spawn(self._task, flintApi, self.stop)

    def _task(self, flint, stop):
        key = get_flint_key()
        with safe_rpc_server(flint) as (task, url):
            with maintain_value(key, url):
                gevent.wait([stop, task], count=1)

    def join(self):
        self.stop.set_result(True)
        self.thread.join()


class FlintWindow(qt.QMainWindow):
    """"Main Flint window"""

    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self, parent=parent)
        self.setAttribute(qt.Qt.WA_QuitOnClose, True)

        self.__flintState: flint_model.FlintState

        central_widget = qt.QWidget(self)

        tabs = qt.QTabWidget(central_widget)
        self.__tabs = tabs

        self.setCentralWidget(tabs)
        self.__initMenus()
        self.__initLogWindow()

    def setFlintState(self, flintState):
        self.__flintState = flintState
        self.updateTitle()

    def tabs(self):
        # FIXME: Have to be removed as it is not really an abstraction
        return self.__tabs

    def __initLogWindow(self):
        logWindow = qt.QDialog(self)
        logWidget = LogWidget(logWindow)
        qt.QVBoxLayout(logWindow)
        logWindow.layout().addWidget(logWidget)
        logWindow.setAttribute(qt.Qt.WA_QuitOnClose, False)
        logWindow.setWindowTitle("Log messages")
        self.__logWindow = logWindow
        logWidget.connect_logger(ROOT_LOGGER)

    def __initMenus(self):
        exitAction = qt.QAction("&Exit", self)
        exitAction.setShortcut("Ctrl+Q")
        exitAction.setStatusTip("Exit flint")
        exitAction.triggered.connect(self.close)
        showLogAction = qt.QAction("Show &log", self)
        showLogAction.setShortcut("Ctrl+L")
        showLogAction.setStatusTip("Show log window")

        showLogAction.triggered.connect(self.showLogDialog)
        menubar = self.menuBar()
        fileMenu = menubar.addMenu("&File")
        fileMenu.addAction(exitAction)
        windowMenu = menubar.addMenu("&Windows")
        windowMenu.addAction(showLogAction)

        helpMenu = menubar.addMenu("&Help")

        action = qt.QAction("&About", self)
        action.setStatusTip("Show the application's About box")
        action.triggered.connect(self.showAboutBox)
        helpMenu.addAction(action)

        action = qt.QAction("&IPython console", self)
        action.setStatusTip("Show a IPython console (for debug purpose)")
        action.triggered.connect(self.openDebugConsole)
        helpMenu.addAction(action)

    def openDebugConsole(self):
        """Open a new debug console"""
        try:
            from silx.gui.console import IPythonDockWidget
        except ImportError:
            ROOT_LOGGER.debug("Error while loading IPython console", exc_info=True)
            ROOT_LOGGER.error("IPython not available")
            return

        available_vars = {"flintState": self.__flintState, "window": self}
        banner = (
            "The variable 'flintState' and 'window' are available.\n"
            "Use the 'whos' and 'help(flintState)' commands for more information.\n"
            "\n"
        )
        widget = IPythonDockWidget(
            parent=self, available_vars=available_vars, custom_banner=banner
        )
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
        widget.show()

    def showLogDialog(self):
        """Show the log dialog of Flint"""
        self.__logWindow.show()

    def showAboutBox(self):
        """Show the about box of Flint"""
        from .widgets.about import About

        About.about(self, "Flint")

    def createTab(self, label, widgetClass=qt.QWidget):
        # FIXME: The parent have to be set
        widget = widgetClass()
        self.__tabs.addTab(widget, label)
        return widget

    def removeTab(self, widget):
        index = self.__tabs.indexOf(widget)
        self.__tabs.removeTab(index)

    def createLiveWindow(self):
        window: qt.QMainWindow = self.createTab("Live scan", qt.QMainWindow)
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
        return window

    def updateTitle(self):
        # FIXME: Should be private
        # FIXME: Should be triggered by signal
        flint = self.__flintState.flintApi()
        session_name = flint.get_session()

        if not session_name:
            session = "no session attached."
        else:
            session = "attached to '%s`" % session_name
        title = "Flint (PID={}) - {}".format(os.getpid(), session)
        self.setWindowTitle(title)

    def initFromSettings(self):
        settings = self.__flintState.settings()
        # resize window to 70% of available screen space, if no settings
        settings.beginGroup("main-window")
        pos = qt.QDesktopWidget().availableGeometry(self).size() * 0.7
        w = pos.width()
        h = pos.height()
        self.resize(settings.value("size", qt.QSize(w, h)))
        self.move(settings.value("pos", qt.QPoint(3 * w / 14.0, 3 * h / 14.0)))
        settings.endGroup()

        manager = self.__flintState.mainManager()
        settings.beginGroup("live-window")
        state = settings.value("workspace", None)
        if state is not None:
            try:
                manager.restoreWorkspace(state)
                ROOT_LOGGER.info("Workspace restored")
            except Exception:
                ROOT_LOGGER.error("Error while restoring the workspace", exc_info=True)
                self.__feed_default_workspace()
        else:
            self.__feed_default_workspace()
        settings.endGroup()

    def saveToSettings(self):
        settings = self.__flintState.settings()
        settings.beginGroup("main-window")
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()

        manager = self.__flintState.mainManager()
        settings.beginGroup("live-window")
        try:
            state = manager.saveWorkspace(includePlots=False)
            settings.setValue("workspace", state)
            ROOT_LOGGER.info("Workspace saved")
        except Exception:
            ROOT_LOGGER.error("Error while saving the workspace", exc_info=True)
        settings.endGroup()

        settings.sync()


class Flint:
    """Flint interface, meant to be exposed through an RPC server."""

    # FIXME: Everything relative to GUI should be removed in order to only provide
    # RPC functions

    _id_generator = itertools.count()

    def __init__(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        self.plot_dict: Dict[object, qt.QWidget] = {}
        self.plot_title: Dict[object, str] = {}
        self.data_event = collections.defaultdict(dict)
        self.selector_dict = collections.defaultdict(list)
        self.data_dict = collections.defaultdict(dict)
        self.scans_watch_task = None
        self._session_name = None

        connection = get_default_connection()
        address = connection.get_redis_connection_address()
        self._qt_redis_connection = connection.create_redis_connection(address=address)

    def get_flint_model(self) -> flint_model.FlintState:
        return self.__flintModel

    def __feed_default_workspace(self):
        # FIXME: Here we can feed the workspace with something persistent
        flintModel = self.get_flint_model()
        workspace = flintModel.workspace()
        window = flintModel.liveWindow()

        curvePlotWidget = CurvePlotWidget(parent=window)
        curvePlotWidget.setFlintModel(flintModel)
        curvePlotWidget.setObjectName("curve1-dock")
        curvePlotWidget.setWindowTitle("Curve1")
        curvePlotWidget.setFeatures(
            curvePlotWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )
        curvePlotWidget.widget().setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        workspace.addWidget(curvePlotWidget)
        window.addDockWidget(qt.Qt.RightDockWidgetArea, curvePlotWidget)

    def create_new_id(self):
        return next(self._id_generator)

    def redis_session_info(self):
        return dict(
            session_name=self._session_name, redis_connection=self._qt_redis_connection
        )

    def get_session(self):
        return self._session_name

    def _spawn_scans_session_watch(self, session_name, clean_redis=False):
        # FIXME: It could be mostly moved into scan_manager
        if clean_redis:
            clean_all_redis_connection()

        ready_event = gevent.event.Event()

        scanManager = self.__flintModel.scanManager()
        task = gevent.spawn(
            watch_session_scans,
            session_name,
            scanManager.new_scan,
            scanManager.new_scan_child,
            scanManager.new_scan_data,
            scanManager.end_scan,
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

        # FIXME: session update have to be triggered by event from FlintModel
        mainWindow = self.__flintModel.mainWindow()
        mainWindow.updateTitle()

    def wait_data(self, master, plot_type, index):
        ev = (
            self.data_event[master]
            .setdefault(plot_type, {})
            .setdefault(index, gevent.event.Event())
        )
        ev.wait(timeout=3)

    def get_live_scan_data(self, channel_name):
        model = self.get_flint_model()
        scan = model.currentScan()
        if scan is None:
            raise Exception("No scan available")
        channel = scan.getChannelByName(channel_name)
        if channel is None:
            raise Exception(f"Channel {channel_name} is not part of this scan")
        data = channel.data()
        if data is None:
            # Just no data
            return None
        return data.array()

    def get_live_scan_plot(self, channel_name, plot_type):
        assert plot_type in ["scatter", "image", "curve", "mca"]

        plot_class = {
            "scatter": plot_item_model.ScatterPlot,
            "image": plot_item_model.ImagePlot,
            "mca": plot_item_model.McaPlot,
            "curve": plot_item_model.CurvePlot,
        }[plot_type]

        scan = self.__flintModel.currentScan()
        if scan is None:
            raise Exception("No scan displayed")

        channel = scan.getChannelByName(channel_name)
        if channel is None:
            raise Exception(
                "The channel '%s' is not part of the current scan" % channel_name
            )

        workspace = self.__flintModel.workspace()
        for iwidget, widget in enumerate(workspace.widgets()):
            plot = widget.plotModel()
            if plot is None:
                continue
            if not isinstance(plot, plot_class):
                continue
            if model_helper.isChannelDisplayedAsValue(plot, channel):
                return f"live:{iwidget}"

        # FIXME: Here we could create a specific plot
        raise Exception("The channel '%s' is not part of any plots" % channel_name)

    def wait_end_of_scan(self):
        scanManager = self.__flintModel.scanManager()
        scanManager.wait_end_of_scan()

    def run_method(self, plot_id, method, args, kwargs):
        plot = self._get_plot_widget(plot_id)
        method = getattr(plot, method)
        return method(*args, **kwargs)

    # Plot management

    def add_plot(self, cls_name, name=None):
        plot_id = self.create_new_id()
        if not name:
            name = "Plot %d" % plot_id
        new_tab_widget = self.__flintModel.mainWindow().createTab(name)
        qt.QVBoxLayout(new_tab_widget)
        cls = getattr(silx_plot, cls_name)
        plot = cls(new_tab_widget)
        self.plot_dict[plot_id] = plot
        self.plot_title[plot_id] = name
        new_tab_widget.layout().addWidget(plot)
        plot.show()
        return plot_id

    def get_plot_name(self, plot_id):
        return self.plot_title[plot_id]

    def remove_plot(self, plot_id):
        plot = self.plot_dict.pop(plot_id)
        plotParent = plot.parent()
        window = self.__flintModel.mainWindow()
        window.removeTab(plotParent)
        plot.close()

    def get_interface(self, plot_id):
        plot = self._get_plot_widget(plot_id)
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
        plot = self._get_plot_widget(plot_id)
        # Hackish legend handling
        if "legend" not in kwargs and method.startswith("add"):
            kwargs["legend"] = " -> ".join(names)
        # Get the data to plot
        args = tuple(self.data_dict[plot_id][name] for name in names)
        method = getattr(plot, method)
        # Plot
        method(*args, **kwargs)

    def deselect_data(self, plot_id, names):
        plot = self._get_plot_widget(plot_id)
        legend = " -> ".join(names)
        plot.remove(legend)

    def clear_data(self, plot_id):
        del self.data_dict[plot_id]
        plot = self._get_plot_widget(plot_id)
        plot.clear()

    def _get_plot_widget(self, plot_id):
        if isinstance(plot_id, str) and plot_id.startswith("live:"):
            workspace = self.__flintModel.workspace()
            try:
                iwidget = int(plot_id[5:])
                if iwidget < 0:
                    raise ValueError()
            except Exception:
                raise ValueError(f"'{plot_id}' is not a valid plot_id")
            widgets = list(workspace.widgets())
            if iwidget >= len(widgets):
                raise ValueError(f"'{plot_id}' is not anymore available")
            widget = widgets[iwidget]
            if not hasattr(widget, "_silxPlot"):
                raise ValueError(
                    f"The widget associated to '{plot_id}' do not provide a silx API"
                )
            return widget._silxPlot()

        return self.plot_dict[plot_id]

    # User interaction

    def select_shapes(self, plot_id, initial_shapes=(), timeout=None):
        plot = self._get_plot_widget(plot_id)
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
        plot = self._get_plot_widget(plot_id)
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


def create_flint_model(settings) -> flint_model.FlintState:
    """"
    Create Flint class and main windows without interaction with the
    environment.
    """
    flintModel = flint_model.FlintState()
    flintModel.setSettings(settings)

    flintApi = Flint(flintModel)
    flintModel.setFlintApi(flintApi)

    flintWindow = FlintWindow(None)
    flintWindow.setFlintState(flintModel)
    flintModel.setMainWindow(flintWindow)

    liveWindow = flintWindow.createLiveWindow()
    flintModel.setLiveWindow(liveWindow)

    manager = ManageMainBehaviours(flintModel)
    manager.setFlintModel(flintModel)
    flintModel.setMainManager(manager)

    # Live GUI

    scanStatusWidget = ScanStatus(liveWindow)
    scanStatusWidget.setObjectName("scan-status-dock")
    scanStatusWidget.setFlintModel(flintModel)
    scanStatusWidget.setFeatures(
        scanStatusWidget.features() & ~qt.QDockWidget.DockWidgetClosable
    )
    flintModel.setLiveStatusWidget(scanStatusWidget)
    liveWindow.addDockWidget(qt.Qt.LeftDockWidgetArea, scanStatusWidget)

    propertyWidget = MainPropertyWidget(liveWindow)
    propertyWidget.setObjectName("property-dock")
    propertyWidget.setFeatures(
        propertyWidget.features() & ~qt.QDockWidget.DockWidgetClosable
    )
    flintModel.setPropertyWidget(propertyWidget)
    liveWindow.splitDockWidget(scanStatusWidget, propertyWidget, qt.Qt.Vertical)

    size = scanStatusWidget.sizeHint()
    scanStatusWidget.widget().setFixedHeight(size.height())
    scanStatusWidget.widget().setMinimumWidth(200)

    scanStatusWidget.widget().setSizePolicy(
        qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred
    )
    propertyWidget.widget().setSizePolicy(
        qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding
    )

    # Workspace

    workspace = flint_model.Workspace()
    flintModel.setWorkspace(workspace)

    # Everything is there we can read the settings

    flintWindow.initFromSettings()

    # Finally scan manager

    scanManager = scan_manager.ScanManager(flintModel)
    flintModel.setScanManager(scanManager)

    return flintModel


def parse_options():
    """
    Returns parsed command line argument as an `options` object.

    :raises ExitException: In case of the use of `--help` in the comman line
    """
    parser = ArgumentParser()
    config.configure_parser_arguments(parser)
    options = parser.parse_args()
    return options


def set_global_settings(settings: qt.QSettings, options):
    """"Set the global settings from command line options and local user
    settings.

    This function also update the local user settings from the command line
    options.
    """
    if options.clear_settings:
        # Clear all the stored keys
        settings.clear()

    try:
        import matplotlib
    except ImportError:
        matplotlib = None

    def update_and_return(option, setting_key, default_to_remove):
        """Update a single setting from the command line option and returns the
        final value."""
        if option is None:
            value = settings.value(setting_key, None)
        else:
            if option == default_to_remove:
                settings.remove(setting_key)
                value = None
            else:
                settings.setValue(setting_key, option)
                value = option
        return value

    if matplotlib:
        settings.beginGroup("matplotlib")
        value = update_and_return(options.matplotlib_dpi, "dpi", 100)
        if value is not None:
            matplotlib.rcParams["figure.dpi"] = float(value)
        settings.endGroup()

    if options.opengl:
        silx.config.DEFAULT_PLOT_BACKEND = "opengl"


def main():
    logging.basicConfig(level=logging.INFO)
    logging.captureWarnings(True)
    ROOT_LOGGER.level = logging.INFO

    options = parse_options()
    if options.debug:
        logging.root.setLevel(logging.DEBUG)
    else:
        silx_log = logging.getLogger("silx")
        silx_log.setLevel(logging.WARNING)

    need_gevent_loop = True
    if options.gevent_poll:
        if poll_patch:
            need_gevent_loop = False
            poll_patch.init(1)
        else:
            ROOT_LOGGER.error("gevent_poll requested but `poll_patch` was not loaded.")
            ROOT_LOGGER.warning("A QTimer for gevent loop will be created instead.")
            need_gevent_loop = True

    # Avoid warning in case of locked loop (debug mode/ipython mode)
    PyQt5.QtCore.pyqtRemoveInputHook()

    qapp = qt.QApplication(sys.argv)
    qapp.setApplicationName("flint")
    qapp.setOrganizationName("ESRF")
    qapp.setOrganizationDomain("esrf.eu")
    settings = qt.QSettings(
        qt.QSettings.IniFormat, qt.QSettings.UserScope, qapp.applicationName()
    )
    set_global_settings(settings, options)

    bliss.flint.resources.silx_integration()

    flintModel = create_flint_model(settings)
    flintWindow = flintModel.mainWindow()
    qapp.aboutToQuit.connect(flintWindow.saveToSettings)

    if options.simulator:
        from bliss.flint.simulator.acquisition import AcquisitionSimulator
        from bliss.flint.simulator.simulator_widget import SimulatorWidget

        display = SimulatorWidget(flintWindow)
        display.setFlintModel(flintModel)
        simulator = AcquisitionSimulator(display)
        scanManager = flintModel.scanManager()
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
    ctrlc_timer = qt.QTimer()
    ctrlc_timer.start(500)
    ctrlc_timer.timeout.connect(lambda: None)

    if need_gevent_loop:
        gevent_timer = qt.QTimer()
        gevent_timer.start(10)
        gevent_timer.timeout.connect(lambda: gevent.sleep(0.01))
        ROOT_LOGGER.info("gevent based on QTimer")
    else:
        ROOT_LOGGER.info("gevent use poll patched")

    # RPC service of the Flint API
    server = FlintServer(flintModel.flintApi())

    # FIXME: why using a timer?
    single_shot = qt.QTimer()
    single_shot.setSingleShot(True)
    single_shot.timeout.connect(flintWindow.show)
    single_shot.start(0)

    try:
        sys.exit(qapp.exec_())
    finally:
        server.join()


if __name__ == "__main__":
    main()
