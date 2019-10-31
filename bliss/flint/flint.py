# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Dict

import sys
import logging
import warnings
import itertools
import functools
import contextlib
import collections
import signal

import gevent.event
from argparse import ArgumentParser

from bliss.data.scan import watch_session_scans
from bliss.config.conductor.client import get_default_connection
from bliss.config.conductor.client import get_redis_connection
from bliss.config.conductor.client import clean_all_redis_connection

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
from bliss.flint.helper.manager import ManageMainBehaviours
from bliss.flint.helper import scan_manager
from bliss.flint.helper import model_helper
from bliss.flint.model import plot_item_model
from bliss.flint.model import flint_model
from bliss.flint import config
from bliss.flint.helper.rpc_server import FlintServer
from bliss.flint.flint_window import FlintWindow

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
        key = config.get_flint_key()
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
            functools.partial(self._selection_finished, done_event=done_event)
        )

        try:
            return done_event.get(timeout=timeout)
        finally:
            plot.removeDockWidget(dock)

    def _selection_finished(self, selections, done_event=None):
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
