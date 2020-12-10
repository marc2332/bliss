# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import silx
import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot import PlotWidget
from silx.gui.plot import PlotWindow

_logger = logging.getLogger(__name__)


class OpenGLAction(qt.QAction):
    """QAction controlling rendering of all the :class:`.PlotWidget`.
    """

    def __init__(self, parent=None):
        # Uses two images for checked/unchecked states
        self._states = {
            "opengl": (
                icons.getQIcon("backend-opengl"),
                "Disable OpenGL plots",
                "OpenGL rendering (fast)\nClick to disable OpenGL",
            ),
            "matplotlib": (
                icons.getQIcon("backend-opengl"),
                "Enable OpenGL plots",
                "Matplotlib rendering (safe)\nClick to enable OpenGL",
            ),
            "unknown": (
                icons.getQIcon("backend-opengl"),
                "Enable OpenGL plots",
                "Custom rendering\nClick to enable OpenGL",
            ),
        }

        super(OpenGLAction, self).__init__(parent)
        self.setCheckable(True)
        self.triggered.connect(self._actionTriggered)
        self.updateState()

    def updateState(self):
        name = self._getBackendName()
        self.__state = name
        icon, text, tooltip = self._states[name]
        self.setIcon(icon)
        self.setToolTip(tooltip)
        self.setText(text)
        self.setChecked(name == "opengl")

    def _getBackendName(self):
        name = silx.config.DEFAULT_PLOT_BACKEND
        if isinstance(name, (list, tuple)):
            name = name[0]
        if "opengl" in name:
            return "opengl"
        elif "matplotlib" in name:
            return "matplotlib"
        else:
            return "unknown"

    def _actionTriggered(self, checked=False):
        name = self._getBackendName()
        if self.__state != name:
            # There is no event to know the backend was updated
            # So here we check if there is a mismatch between the displayed state
            # and the real state of the widget
            self.updateState()
            return
        if name != "opengl":
            from silx.gui.utils import glutils

            result = glutils.isOpenGLAvailable()
            # if not result:
            if False:
                qt.QMessageBox.critical(
                    None, "OpenGL rendering is not available", result.error
                )
                # Uncheck if needed
                self.updateState()
                return
            self._updatePlots("opengl")
        else:
            self._updatePlots("matplotlib")
        self.updateState()

    def _updatePlots(self, backend):
        qapp = qt.QApplication.instance()
        error = None
        for widget in qapp.allWidgets():
            if not isinstance(widget, (PlotWidget, PlotWindow)):
                continue
            try:
                widget.setBackend(backend)
            except Exception as e:
                error = e

        if error is not None:
            _logger.error(
                "Error while changing the silx plot backend to '%s'",
                backend,
                exc_info=error,
            )
        else:
            silx.config.DEFAULT_PLOT_BACKEND = backend
