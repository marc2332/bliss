# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Main entry for Flint application.

This module provide a `main``function which initialize all the main components.

Here is a view of this architecture and the way it interact with it's
environment.

.. image:: _static/flint/flint_architecture.svg
    :alt: Scan model
    :align: center

- A :class:`~bliss.flint.model.flint_model.FlintState` is created to provide all the
  available process and data own by Flint.
- Other objects from the package :class:`~bliss.flint.model` provides the modelization
  of concepts Flint have to deal with (scans, plots, curves...)
- A :class:`~bliss.flint.helper.manager.ManageMainBehaviours` have the responsibility
  to react to events and update the model or dispatch it to other managers
- A :class:`~bliss.flint.flint_window.FlintWindow` provides the user interaction on
  top of the modelization (basically the view, in MVC design).
- A :class:`~bliss.flint.helper.scan_manager.ScanManager` deaLS with events from Redis,
  and feeds the modelization with the state of the scans acquired by BLISS.
- Finally :class:`~bliss.flint.flint_api.FlintApi` provides a command line API to
  interact with flint. It is served by a generic server. On client side (BLISS),
  this server and it's API is reachable using :func:`bliss.common.plot.get_flint`.
- A user can then interact with Flint using both command line API or GUI.
"""

import sys
import logging
import signal

import gevent
from argparse import ArgumentParser

try:
    from bliss.flint import poll_patch
except ImportError:
    poll_patch = None

# Enforce loading of PyQt5
# In case silx/matplotlib tries to import PySide, PyQt4...
import PyQt5.QtCore

import silx
from silx.gui import qt

import bliss.flint.resources
from bliss.flint.widgets.property_widget import MainPropertyWidget
from bliss.flint.widgets.scan_status import ScanStatus
from bliss.flint.helper.manager import ManageMainBehaviours
from bliss.flint.helper import scan_manager
from bliss.flint.model import flint_model
from bliss.flint import config
from bliss.flint.helper.rpc_server import FlintServer
from bliss.flint.flint_window import FlintWindow
from bliss.flint.flint_api import FlintApi

ROOT_LOGGER = logging.getLogger()
"""Application logger"""


def create_flint_model(settings) -> flint_model.FlintState:
    """"
    Create Flint class and main windows without interaction with the
    environment.
    """
    flintModel = flint_model.FlintState()
    flintModel.setSettings(settings)

    flintApi = FlintApi(flintModel)
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
    manager.initRedis()

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


def process_gevent():
    """Process gevent in case of QTimer triggering it."""
    try:
        gevent.sleep(0.01)
    except Exception:
        ROOT_LOGGER.critical("Uncaught exception from gevent", exc_info=True)


def handle_exception(exc_type, exc_value, exc_traceback):
    """Catch exceptions which was uncaught."""
    ROOT_LOGGER.critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )


def initApplication(argv):
    qapp = qt.QApplication.instance()
    if qapp is None:
        # Do not recreate OpenGL context when docking/undocking windows
        qt.QCoreApplication.setAttribute(qt.Qt.AA_ShareOpenGLContexts)
        qapp = qt.QApplication(argv)
    qapp.setApplicationName("flint")
    qapp.setOrganizationName("ESRF")
    qapp.setOrganizationDomain("esrf.eu")
    bliss.flint.resources.silx_integration()
    return qapp


def config_logging():
    # Basic default formatter
    fs = logging.BASIC_FORMAT
    dfs = None
    formatter = logging.Formatter(fs, dfs)

    # Logs level < ERROR to stdout and llevel >= ERROR to stderr
    # As result bliss console will display a better result
    handler_stdout = logging.StreamHandler(sys.stdout)
    handler_stdout.setFormatter(formatter)
    handler_stdout.setLevel(logging.DEBUG)
    handler_stdout.addFilter(lambda record: record.levelno < logging.ERROR)
    handler_stderr = logging.StreamHandler()
    handler_stderr.setFormatter(formatter)
    handler_stderr.setLevel(logging.ERROR)
    ROOT_LOGGER.addHandler(handler_stdout)
    ROOT_LOGGER.addHandler(handler_stderr)

    logging.captureWarnings(True)
    ROOT_LOGGER.level = logging.INFO


def main():
    config_logging()

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

    qapp = initApplication(sys.argv)
    settings = qt.QSettings(
        qt.QSettings.IniFormat, qt.QSettings.UserScope, qapp.applicationName()
    )
    set_global_settings(settings, options)

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
        gevent_timer.timeout.connect(process_gevent)
        ROOT_LOGGER.info("gevent based on QTimer")
    else:
        ROOT_LOGGER.info("gevent use poll patched")

    # RPC service of the Flint API
    server = FlintServer(flintModel.flintApi())

    # FIXME: why using a timer?
    single_shot = qt.QTimer()
    single_shot.setSingleShot(True)

    def start():
        flintWindow.show()
        flintModel.mainManager().setFlintStarted()

    single_shot.timeout.connect(start)
    single_shot.start(0)

    try:
        sys.exit(qapp.exec_())
    finally:
        server.join()


if __name__ == "__main__":
    main()
