# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Main entry for Flint application.

This module provide a `main` function which initialize all the main components.

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
import functools

import gevent
from argparse import ArgumentParser

try:
    from bliss.flint import poll_patch
except ImportError:
    poll_patch = None

# Enforce loading of PyQt5
# In case silx/matplotlib tries to import PySide, PyQt4...
import PyQt5.QtCore  # noqa

import silx  # noqa

# Have to be imported early to prevent segfault (noticed with WSL)
# See https://github.com/silx-kit/silx/issues/3232
import silx.gui.plot.matplotlib  # noqa
from silx.gui import qt
from bliss.flint.model import flint_model


ROOT_LOGGER = logging.getLogger()
"""Application logger"""

SAVE_OPENGL_CONFIG = True


def patch_qt():
    """Patch Qt bindings in order simplify the integration.
    """
    global PyQt5
    # Avoid warning in case of locked loop (debug mode/ipython mode)
    PyQt5.QtCore.pyqtRemoveInputHook()

    if PyQt5.QtCore.qVersion() == "5.9.7":
        # PyQt5 5.9.7 is using unicode while it is not anymore needed. This
        # removes a warning by fixing the issue.
        try:
            import PyQt5.uic.objcreator

            PyQt5.uic.objcreator.open = lambda f, flag: open(f, flag.replace("U", ""))
        except ImportError:
            pass


def create_flint_model(settings) -> flint_model.FlintState:
    """"
    Create Flint classes and main windows without interaction with the
    environment.
    """
    from bliss.flint.manager.manager import ManageMainBehaviours
    from bliss.flint.flint_window import FlintWindow
    from bliss.flint.flint_api import FlintApi

    flintModel = flint_model.FlintState()
    flintModel.setSettings(settings)

    flintApi = FlintApi(flintModel)
    flintModel.setFlintApi(flintApi)

    flintWindow = FlintWindow(None)
    flintWindow.setFlintModel(flintModel)
    flintModel.setMainWindow(flintWindow)

    liveWindow = flintWindow.createLiveWindow()
    flintModel.setLiveWindow(liveWindow)

    manager = ManageMainBehaviours(flintModel)
    manager.setFlintModel(flintModel)
    flintModel.setMainManager(manager)
    liveWindow.setFlintModel(flintModel)
    flintWindow.initMenus()

    # Workspace
    workspace = flint_model.Workspace()
    flintModel.setWorkspace(workspace)

    return flintModel


def start_flint(flintModel: flint_model.FlintState, options, splash):
    """
    This have to be executed after the start of the main Qt loop.

    It looks to fix initial layout issue.
    """
    from bliss.flint.manager import scan_manager

    flintWindow = flintModel.mainWindow()
    manager = flintModel.mainManager()

    # Everything is there we can read the settings
    flintWindow.initFromSettings()
    manager.initRedis()
    # flintWindow.show()

    # Finally scan manager
    scanManager = scan_manager.ScanManager(flintModel)
    flintModel.setScanManager(scanManager)

    if options.bliss_session is not None:
        manager = flintModel.mainManager()
        result = manager.updateBlissSessionName(options.bliss_session)
        if not result:
            msg = f"Impossible to connect to the session '{options.bliss_session}'"
            qt.QMessageBox.critical(flintWindow, "Session error", msg)

    # Flag that flint is started
    ROOT_LOGGER.info("Flint started")
    manager.setFlintStarted()

    flintWindow.setVisible(True)

    liveWindow = flintModel.liveWindow()
    liveWindow.postInit()

    # Close the spash screen
    splash.finish(flintWindow)


def parse_options():
    """
    Returns parsed command line argument as an `options` object.

    :raises ExitException: In case of the use of `--help` in the comman line
    """
    from bliss.flint import config

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
    ROOT_LOGGER.debug("Set global settings...")

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

    if options.opengl is not None:
        if options.opengl:
            from silx.gui.utils import glutils

            result = glutils.isOpenGLAvailable()
            if result:
                silx.config.DEFAULT_PLOT_BACKEND = "opengl"
            else:
                ROOT_LOGGER.warning("OpenGL is not available: %s", result.error)
                ROOT_LOGGER.warning(
                    "Switch back to matplotlib backend for this execusion"
                )
                silx.config.DEFAULT_PLOT_BACKEND = "matplotlib"
        else:
            silx.config.DEFAULT_PLOT_BACKEND = "matplotlib"
            ROOT_LOGGER.warning("Enforce matplotlib backend for this execusion")
        # This setting is only used for this execusion
        SAVE_OPENGL_CONFIG = False
    else:
        settings.beginGroup("silx")
        useOpengl = settings.value("use-opengl", False, type=bool)
        settings.endGroup()

        if useOpengl:
            from silx.gui.utils import glutils

            result = glutils.isOpenGLAvailable()
            if result:
                silx.config.DEFAULT_PLOT_BACKEND = "opengl"
            else:
                ROOT_LOGGER.warning("OpenGL is not available: %s", result.error)
                ROOT_LOGGER.warning("Switch back to matplotlib backend")
                silx.config.DEFAULT_PLOT_BACKEND = "matplotlib"
                # This can be the case when connecting through SSH
                # So try to not overwrite the default config
                SAVE_OPENGL_CONFIG = False
        else:
            silx.config.DEFAULT_PLOT_BACKEND = "matplotlib"

    ROOT_LOGGER.debug("Global settings set")


def save_global_settings(flintModel, options):
    """Save the global settings into the config file"""
    ROOT_LOGGER.debug("Save global settings...")

    settings = flintModel.settings()
    flintWindow = flintModel.mainWindow()
    flintWindow.saveToSettings()

    settings.beginGroup("silx")
    if SAVE_OPENGL_CONFIG:
        # If there was no config for this execusion we can save the current state
        backend = silx.config.DEFAULT_PLOT_BACKEND
        settings.setValue("use-opengl", backend == "opengl")
    settings.endGroup()

    manager = flintModel.mainManager()
    try:
        manager.saveBeforeClosing()
    except Exception:
        ROOT_LOGGER.error("Error while saving the workspace", exc_info=True)

    settings.sync()
    ROOT_LOGGER.debug("Global settings saved")


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


def initApplication(argv, options, settings: qt.QSettings):
    qapp = qt.QApplication.instance()
    if qapp is None:
        settings.beginGroup("qapplication")
        settings_share_opengl_contexts = settings.value(
            "share-opengl-contexts", True, bool
        )
        settings.endGroup()

        # Command line option override the settings
        if options.share_opengl_contexts is not None:
            do_share_opengl_contexts = options.share_opengl_contexts
        else:
            do_share_opengl_contexts = settings_share_opengl_contexts

        if do_share_opengl_contexts:
            # This allows to reuse OpenGL context when docking/undocking windows
            # Can be disabled by command line in order to prevent segfault in
            # some environments
            ROOT_LOGGER.debug("Setup AA_ShareOpenGLContexts")
            qt.QCoreApplication.setAttribute(qt.Qt.AA_ShareOpenGLContexts)
        ROOT_LOGGER.debug("Create Qt application")
        qapp = qt.QApplication(argv)

    qapp.setApplicationName(settings.applicationName())
    qapp.setOrganizationName(settings.organizationName())
    qapp.setOrganizationDomain("esrf.eu")

    import bliss.flint.resources
    from silx.gui import icons

    bliss.flint.resources.silx_integration()
    flintIcon = icons.getQIcon("flint:logo/bliss_logo_small")
    qapp.setWindowIcon(flintIcon)

    # Care of the formatting for numbers (no coma)
    qt.QLocale.setDefault(qt.QLocale.c())
    ROOT_LOGGER.debug("Qt application initialized")
    return qapp


def config_logging(options):
    # Basic default formatter
    fs = logging.BASIC_FORMAT
    dfs = None
    formatter = logging.Formatter(fs, dfs)

    # Logs level < ERROR to stdout and level >= ERROR to stderr
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

    if options.log_file:
        handler_file = logging.FileHandler(filename=options.log_file, mode="w")
        handler_file.setFormatter(formatter)
        handler_file.setLevel(logging.INFO)
        ROOT_LOGGER.addHandler(handler_file)

    logging.captureWarnings(True)


def create_spash_screen():
    import silx.resources

    splash = qt.QSplashScreen()
    try:
        filename = silx.resources.resource_filename("flint:logo/splashscreen.png")
        if filename is not None:
            splash.setPixmap(qt.QPixmap(filename))
    except Exception:
        ROOT_LOGGER.error("Error while loading splash screen")
    splash.show()
    splash.showMessage("Loading Flint...", qt.Qt.AlignLeft, qt.Qt.black)
    return splash


def main():
    options = parse_options()
    if options.debug:
        ROOT_LOGGER.setLevel(logging.DEBUG)
        mpl_log = logging.getLogger("matplotlib")
        mpl_log.setLevel(logging.INFO)
    else:
        ROOT_LOGGER.setLevel(logging.INFO)
        silx_log = logging.getLogger("silx")
        silx_log.setLevel(logging.WARNING)

    config_logging(options)

    need_gevent_loop = True
    if options.gevent_poll:
        if poll_patch:
            need_gevent_loop = False
            poll_patch.init(1)
        else:
            ROOT_LOGGER.error("gevent_poll requested but `poll_patch` was not loaded.")
            ROOT_LOGGER.warning("A QTimer for gevent loop will be created instead.")
            need_gevent_loop = True

    # Patch qt binding to remove few warnings
    patch_qt()

    settings = qt.QSettings(
        qt.QSettings.IniFormat, qt.QSettings.UserScope, "ESRF", "flint"
    )

    qapp = initApplication(sys.argv, options, settings)
    set_global_settings(settings, options)

    splash = create_spash_screen()

    flintModel = create_flint_model(settings)
    qapp.aboutToQuit.connect(
        functools.partial(save_global_settings, flintModel, options)
    )

    if options.simulator:
        from bliss.flint.simulator.acquisition import AcquisitionSimulator
        from bliss.flint.simulator.simulator_widget import SimulatorWidget

        flintWindow = flintModel.mainWindow()
        display = SimulatorWidget(flintWindow)
        display.setFlintModel(flintModel)
        simulator = AcquisitionSimulator(display)
        simulator.setFlintModel(flintModel)
        display.setSimulator(simulator)
        display.show()

    sys.excepthook = handle_exception

    def close_service(frame, signum):
        # Try to close the GUI in the normal way
        # This allows pytest-cov to read back the coverage information
        qapp.quit()

    signal.signal(signal.SIGTERM, close_service)

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
    from bliss.flint.helper.rpc_server import FlintServer

    server = FlintServer(flintModel.flintApi())

    # Postpon the real start of flint
    qt.QTimer.singleShot(10, lambda: start_flint(flintModel, options, splash))

    try:
        sys.exit(qapp.exec_())
    finally:
        server.join()

    ROOT_LOGGER.debug("End")


if __name__ == "__main__":
    main()
