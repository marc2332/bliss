# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import os
import tempfile
import base64
import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot import PlotWindow
from silx.gui.plot.actions import PlotAction
from silx.gui.plot.actions import io
from silx.gui.widgets.MultiModeAction import MultiModeAction
from bliss.flint.model import flint_model


_logger = logging.getLogger(__name__)


class ExportAction(MultiModeAction):
    def __init__(self, plot: PlotWindow, parent=None):
        super(ExportAction, self).__init__(parent)
        self._logbookAction = ExportToLogBookAction(plot, self)
        self.addAction(self._logbookAction)
        self.addAction(io.CopyAction(plot, self))
        self.addAction(io.PrintAction(plot, self))
        self.addAction(io.SaveAction(plot, self))

    def setFlintModel(self, state: flint_model.FlintState):
        self._logbookAction.setFlintModel(state)


class ExportToLogBookAction(PlotAction):
    """QAction managing the behavior of saving a current plot into the tango
    metadata logbook.
    """

    def __init__(self, plot: PlotWindow, parent: qt.QWidget):
        super(ExportToLogBookAction, self).__init__(
            plot,
            icon="flint:icons/export-logbook",
            text="Export to logbook",
            tooltip="Export this plot to the logbook",
            triggered=self._actionTriggered,
            parent=parent,
        )
        self.__state: flint_model.FlintState = None

    def setFlintModel(self, state: flint_model.FlintState):
        if self.__state is not None:
            self.__state.tangoMetadataChanged.disconnect(self.__tangoMetadataChanged)
        self.__state = state
        if self.__state is not None:
            self.__state.tangoMetadataChanged.connect(self.__tangoMetadataChanged)
        self.__tangoMetadataChanged()

    def __tangoMetadataChanged(self):
        if self.__state is not None:
            device = self.__state.tangoMetadata()
        else:
            device = None

        if device is None:
            self.setEnabled(False)
            self.setToolTip("No tango-metadata specified")
            return

        if not hasattr(device, "uploadBase64"):
            self.setEnabled(False)
            self.setToolTip(
                "A tango-metadata is specified but does not provide API to upload image"
            )
            return

        self.setEnabled(True)
        self.setToolTip("Export this plot to the logbook")

    def _actionTriggered(self):
        try:
            self._processSave()
        except Exception as e:
            qt.QMessageBox.critical(self.plot, "Error", str(e.args[0]))

    def _processSave(self):
        plot: PlotWindow = self.plot

        try:
            f = tempfile.NamedTemporaryFile(delete=False)
            filename = f.name
            f.close()
            os.unlink(filename)
            plot.saveGraph(filename, fileFormat="png")
            with open(filename, "rb") as f:
                data = f.read()
            os.unlink(filename)
        except:
            _logger.error("Error while creating the screenshot", exc_info=True)
            raise Exception("Error while creating the screenshot")
        data = b"data:image/png;base64," + base64.b64encode(data)
        try:
            tangoMetadata = self.__state.tangoMetadata()
            tangoMetadata.uploadBase64(data)
        except:
            _logger.error("Error while sending the screenshot", exc_info=True)
            raise Exception("Error while sending the screenshot")


class ExportOthersAction(qt.QWidgetAction):
    def __init__(self, plot, parent):
        super(ExportOthersAction, self).__init__(parent)

        menu = qt.QMenu(parent)
        menu.addAction(io.CopyAction(plot, self))
        menu.addAction(io.PrintAction(plot, self))
        menu.addAction(io.SaveAction(plot, self))

        icon = icons.getQIcon("flint:icons/export-others")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Other exports")
        toolButton.setToolTip("Various exports")
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)
