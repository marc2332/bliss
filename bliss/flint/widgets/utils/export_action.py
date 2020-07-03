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
import weakref

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot import PlotWindow
from silx.gui.plot.actions import PlotAction
from silx.gui.plot.actions import io
from bliss.flint.model import flint_model


_logger = logging.getLogger(__name__)


class SwitchAction(qt.QWidgetAction):
    """This action provides a default action from a list of actions.

    The default action can be selected from a drop down list. The last one used
    became the default one.

    The default action is directly usable without using the drop down list.
    """

    def __init__(self, parent=None):
        assert isinstance(parent, qt.QWidget)
        qt.QWidgetAction.__init__(self, parent)
        button = qt.QToolButton(parent)
        button.setPopupMode(qt.QToolButton.MenuButtonPopup)
        self.setDefaultWidget(button)
        self.__button = button
        # In case of action enabled/disabled twice, this attribute can restore
        # a stable state
        self.__lastUserDefault = None

    def getMenu(self):
        """Returns the menu.

        :rtype: qt.QMenu
        """
        button = self.__button
        menu = button.menu()
        if menu is None:
            menu = qt.QMenu(button)
            button.setMenu(menu)
        return menu

    def addAction(self, action):
        """Add a new action to the list.

        :param qt.QAction action: New action
        """
        menu = self.getMenu()
        button = self.__button
        menu.addAction(action)
        if button.defaultAction() is None and action.isEnabled():
            self._setUserDefault(action)
        action.triggered.connect(self._trigger)
        action.changed.connect(self._changed)

    def _changed(self):
        action = self.sender()
        if action.isEnabled():
            if action is self._userDefault():
                # If it was used as default action
                button = self.__button
                defaultAcction = button.defaultAction()
                if defaultAcction is action:
                    return
                # Select it back as the default
                button.setDefaultAction(action)
        else:
            button = self.__button
            defaultAcction = button.defaultAction()
            if defaultAcction is not action:
                return
            # If the action was the default one and is not enabled anymore
            menu = button.menu()
            for action in menu.actions():
                if action.isEnabled():
                    button.setDefaultAction(action)
                    break

    def _trigger(self):
        action = self.sender()
        self._setUserDefault(action)

    def _userDefault(self):
        if self.__lastUserDefault is None:
            return None
        userDefault = self.__lastUserDefault()
        return userDefault

    def _setUserDefault(self, action):
        self.__lastUserDefault = weakref.ref(action)
        button = self.__button
        button.setDefaultAction(action)


class ExportAction(SwitchAction):
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
        elif not hasattr(device, "uploadBase64"):
            self.setEnabled(False)
            self.setToolTip(
                "A tango-metadata is specified but does not provide API to upload image"
            )
        else:
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
