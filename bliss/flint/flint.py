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
from bliss.flint.model import plot_item_model
from bliss.flint.helper import model_helper

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
from bliss.flint.widgets.scan_status import ScanStatus
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

    def __init__(self, mainwin, parent_tab, settings: qt.QSettings):
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
        flintModel.setSettings(settings)
        self.__flintModel = flintModel

        workspace = flint_model.Workspace()
        flintModel.setWorkspace(workspace)
        self.__scanManager = scan_manager.ScanManager(self)

        connection = get_default_connection()
        address = connection.get_redis_connection_address()
        self._qt_redis_connection = connection.create_redis_connection(address=address)
        self.set_title()
        self.init_from_settings()

    def get_flint_model(self) -> flint_model.FlintState:
        return self.__flintModel

    def get_scan_manager(self):
        return self.__scanManager

    def init_from_settings(self):
        settings = self.__flintModel.settings()
        # resize window to 70% of available screen space, if no settings
        settings.beginGroup("main-window")
        pos = qt.QDesktopWidget().availableGeometry(self.mainwin).size() * 0.7
        w = pos.width()
        h = pos.height()
        self.mainwin.resize(settings.value("size", qt.QSize(w, h)))
        self.mainwin.move(settings.value("pos", qt.QPoint(3 * w / 14.0, 3 * h / 14.0)))
        settings.endGroup()

        settings.beginGroup("live-window")
        state = settings.value("workspace", None)
        if state is not None:
            try:
                self.__manager.restoreWorkspace(state)
                ROOT_LOGGER.info("Workspace restored")
            except Exception:
                ROOT_LOGGER.error("Error while restoring the workspace", exc_info=True)
                self.__feed_default_workspace()
        else:
            self.__feed_default_workspace()
        settings.endGroup()

    def save_to_settings(self):
        settings = self.__flintModel.settings()
        settings.beginGroup("main-window")
        settings.setValue("size", self.mainwin.size())
        settings.setValue("pos", self.mainwin.pos())
        settings.endGroup()

        settings.beginGroup("live-window")
        try:
            state = self.__manager.saveWorkspace(includePlots=False)
            settings.setValue("workspace", state)
            ROOT_LOGGER.info("Workspace saved")
        except Exception:
            ROOT_LOGGER.error("Error while saving the workspace", exc_info=True)
        settings.endGroup()

        settings.sync()

    def __create_flint_model(self):
        window: qt.QMainWindow = self.new_tab("Live scan", qt.QMainWindow)
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
        flintModel.setLiveWindow(window)
        flintModel.setFlintApi(self)

        manager = ManageMainBehaviours(flintModel)
        manager.setFlintModel(flintModel)
        self.__manager = manager

        scanStatusWidget = ScanStatus(window)
        scanStatusWidget.setObjectName("scan-status-dock")
        scanStatusWidget.setFlintModel(flintModel)
        scanStatusWidget.setFeatures(
            scanStatusWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )
        flintModel.setLiveStatusWidget(scanStatusWidget)
        window.addDockWidget(qt.Qt.LeftDockWidgetArea, scanStatusWidget)

        propertyWidget = MainPropertyWidget(window)
        propertyWidget.setObjectName("property-dock")
        propertyWidget.setFeatures(
            propertyWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )
        flintModel.setPropertyWidget(propertyWidget)
        window.splitDockWidget(scanStatusWidget, propertyWidget, qt.Qt.Vertical)

        size = scanStatusWidget.sizeHint()
        scanStatusWidget.widget().setFixedHeight(size.height())
        scanStatusWidget.widget().setMinimumWidth(200)

        scanStatusWidget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred
        )
        propertyWidget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding
        )

        return flintModel

    def _manager(self) -> ManageMainBehaviours:
        return self.__manager

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
        self.__scanManager.wait_end_of_scan()

    def new_tab(self, label, widget=qt.QWidget):
        # FIXME: The parent have to be set
        # FIXME: Rename the argument to widgetClass
        widget = widget()
        self.parent_tab.addTab(widget, label)
        return widget

    def run_method(self, plot_id, method, args, kwargs):
        plot = self._get_plot_widget(plot_id)
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
        parent = self._get_plot_widget(plot_id).parent()
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

    flint = Flint(win, tabs, settings)
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
        "--enable-opengl",
        "--gl",
        dest="opengl",
        action="store_true",
        default=False,
        help="Enable OpenGL rendering. It provides a faster rendering for plots "
        "but could have issue with remote desktop (default: matplotlib is used)",
    )
    parser.add_argument(
        "--enable-simulator",
        dest="simulator",
        action="store_true",
        default=False,
        help="Enable scan simulation panel",
    )
    parser.add_argument(
        "--enable-event-interleave",
        dest="event_interleave",
        action="store_true",
        default=False,
        help="Enable interleave of Qt and gevent event loops. "
        "It process efficiently events from fast acquisition scans but could be unstable "
        "(experimental)",
    )
    parser.add_argument(
        "--matplotlib-dpi",
        type=int,
        dest="matplotlib_dpi",
        default=None,
        help="Set the DPI used for the matplotlib backend. "
        "This value will be stored in the user preferences (default: 100)",
    )
    parser.add_argument(
        "--clear-settings",
        action="store_true",
        dest="clear_settings",
        default=False,
        help="Start with cleared local user settings. ",
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
    ROOT_LOGGER.level = logging.INFO

    options = parse_options()
    if options.debug:
        logging.root.setLevel(logging.DEBUG)

    need_gevent_loop = True
    if options.event_interleave:
        if poll_patch:
            need_gevent_loop = False
            poll_patch.init(1)
        else:
            message = "qt/gevent interleave requested but `poll_patch` was not loaded."
            ROOT_LOGGER.error(message)
            ROOT_LOGGER.warning("A QTimer for gevent loop will be created instead")
            need_gevent_loop = True

    qapp = qt.QApplication(sys.argv)
    qapp.setApplicationName("flint")
    qapp.setOrganizationName("ESRF")
    qapp.setOrganizationDomain("esrf.eu")
    settings = qt.QSettings(
        qt.QSettings.IniFormat, qt.QSettings.UserScope, qapp.applicationName()
    )
    set_global_settings(settings, options)

    bliss.flint.resources.silx_integration()

    flint = create_flint(settings)
    qapp.aboutToQuit.connect(flint.save_to_settings)

    if options.simulator:
        from bliss.flint.simulator.acquisition import AcquisitionSimulator
        from bliss.flint.simulator.simulator_widget import SimulatorWidget

        display = SimulatorWidget(flint.mainwin)
        display.setFlintModel(flint.get_flint_model())
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
