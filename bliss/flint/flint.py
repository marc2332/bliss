# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

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
