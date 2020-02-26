# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Helper class to manage the state of the model
"""

from __future__ import annotations
from typing import List
from typing import NamedTuple
from typing import Any
from typing import Dict

import functools

import logging
from silx.gui import qt
from silx.gui import icons

from bliss.config.settings import HashObjSetting
from . import manager
from ..model import flint_model


_logger = logging.getLogger(__name__)


class _WidgetDescriptionCompatibility(NamedTuple):
    """Allow to read the previous way to store the object.

    Was only stored this way before the restart, before 2020-02-26

    Could be remove in few months.
    """

    objectName: str
    windowTitle: str
    className: Any
    modelId: int
    config: Any


class WidgetDescription:
    def __init__(self):
        self.objectName = None
        self.windowTitle = None
        self.className = None
        # FIXME: We should store the full model, instead of a modelId
        #        (pickle can deal with)
        self.modelId = None
        self.config = None

    def __getstate__(self):
        """Inherite the serialization to make sure the object can grow up in the
        future"""
        state: Dict[str, Any] = {}
        state["objectName"] = self.objectName
        state["windowTitle"] = self.windowTitle
        state["className"] = self.className
        state["modelId"] = self.modelId
        state["config"] = self.config
        return state

    def __setstate__(self, state):
        """Inherite the serialization to make sure the object can grow up in the
        future"""
        self.objectName = state.pop("objectName")
        self.windowTitle = state.pop("windowTitle")
        self.className = state.pop("className")
        self.modelId = state.pop("modelId")
        self.config = state.pop("config", None)


class WorkspaceData(dict):
    def setWorkspace(self, workspace: flint_model.Workspace, includePlots: bool):
        plots = {}
        if includePlots:
            for plot in workspace.plots():
                plots[id(plot)] = plot

        widgetDescriptions = []
        for widget in workspace.widgets():
            if includePlots:
                model = widget.plotModel()
                if model is not None:
                    modelId = id(model)
                else:
                    modelId = None
            else:
                modelId = None

            widgetDescription = WidgetDescription()
            widgetDescription.objectName = widget.objectName()
            widgetDescription.windowTitle = widget.windowTitle()
            widgetDescription.className = widget.__class__
            widgetDescription.modelId = modelId
            if hasattr(widget, "configuration"):
                config = widget.configuration()
                widgetDescription.config = config
            widgetDescriptions.append(widgetDescription)

        self["plots"] = plots
        self["widgets"] = widgetDescriptions

    def setLayout(self, layout: qt.QByteArray):
        self["layout"] = layout

    def layout(self):
        return self["layout"]

    def feedWorkspace(self, workspace: flint_model.Workspace, parent: qt.QMainWindow):
        plots: dict = self["plots"]
        widgetDescriptions = self["widgets"]

        for plot in plots.values():
            workspace.addPlot(plot)

        for data in widgetDescriptions:
            if isinstance(data, tuple):
                data = _WidgetDescriptionCompatibility(*data, None)

            widget = data.className(parent)
            widget.setObjectName(data.objectName)
            widget.setWindowTitle(data.windowTitle)
            if hasattr(widget, "setConfiguration") and data.config is not None:
                widget.setConfiguration(data.config)

            # Looks needed to retrieve the right layout with restoreSate
            parent.addDockWidget(qt.Qt.LeftDockWidgetArea, widget)
            if data.modelId is not None:
                plot = plots[data.modelId]
                widget.setPlotModel(plot)
            workspace.addWidget(widget)


class WorkspaceManager(qt.QObject):

    ROOT_KEY = "flint.%s.workspace"

    DEFAULT = "base"

    def mainManager(self) -> manager.ManageMainBehaviours:
        return self.parent()

    def createManagerActions(self, parent: qt.QObject) -> List[qt.QAction]:
        """Create actions to interact with the manager"""
        result = []

        action = qt.QAction(parent)
        action.setText("Load")
        loadMenu = qt.QMenu(parent)
        loadMenu.aboutToShow.connect(self.__feedLoadMenu)
        action.setMenu(loadMenu)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("Remove")
        removeMenu = qt.QMenu(parent)
        removeMenu.aboutToShow.connect(self.__feedRemoveMenu)
        action.setMenu(removeMenu)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("Save as...")
        action.triggered.connect(self.__saveWorkspaceAs)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("Rename as...")
        action.triggered.connect(self.__renameWorkspaceAs)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("Reload layout")
        action.triggered.connect(self.__reloadLayout)
        result.append(action)

        return result

    def __saveAvailableNames(self, names: List[str]):
        settings = self.__getSettings()
        settings["@names"] = names

    def __getAvailableNames(self) -> List[str]:
        settings = self.__getSettings()
        names = settings.get("@names", [])
        return names

    def __feedLoadMenu(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        try:
            names = self.__getAvailableNames()
        except IOError:
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText("Error while loading names")
            menu.addAction(action)
            return

        if len(names) == 0:
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText("No workspace")
            menu.addAction(action)
            return

        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        currentWorkspace = workspace.name()

        for name in names:
            action = qt.QAction(menu)
            action.setText(f"{name}")
            if name == currentWorkspace:
                action.setToolTip("The current workspace")
                action.setCheckable(True)
                action.setChecked(True)
                action.setEnabled(False)
            else:
                action.triggered.connect(
                    functools.partial(self.switchToWorkspace, name)
                )
            menu.addAction(action)

    def __feedRemoveMenu(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        try:
            names = self.__getAvailableNames()
        except IOError:
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText("Error while loading names")
            menu.addAction(action)
            return

        if self.DEFAULT in names:
            names.remove(self.DEFAULT)

        if len(names) == 0:
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText("No workspace")
            menu.addAction(action)
            return

        for name in names:
            action = qt.QAction(menu)
            action.setText(f"{name}")
            action.triggered.connect(functools.partial(self.removeWorkspace, name))
            icon = icons.getQIcon("flint:icons/remove-item")
            action.setIcon(icon)
            menu.addAction(action)

    def __renameWorkspaceAs(self):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        workspace.name()

        name, ok = qt.QInputDialog.getText(
            flintModel.liveWindow(),
            "Rename as",
            "New workspace name:",
            text=workspace.name(),
        )
        if not ok:
            return
        if name == workspace.name():
            return
        self.renameWorkspaceAs(workspace, name)

    def __saveWorkspaceAs(self):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        workspace.name()

        name, ok = qt.QInputDialog.getText(
            flintModel.liveWindow(),
            "Save as",
            "New workspace name:",
            text=workspace.name(),
        )
        if not ok:
            return
        if name == workspace.name():
            return
        self.saveWorkspaceAs(workspace, name)

    def __saveCurrentWorkspaceName(self, name: str):
        settings = self.__getSettings()
        settings["@lastname"] = name

    def __getLastWorkspaceName(self):
        settings = self.__getSettings()
        name = settings.get("@lastname", self.DEFAULT)
        return name

    def loadLastWorkspace(self):
        name = self.__getLastWorkspaceName()
        return self.loadWorkspace(name)

    def __closeWorkspace(self):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        if workspace is None:
            return
        widgets = workspace.popWidgets()
        for w in widgets:
            # Make sure we can create object name without collision
            w.setPlotModel(None)
            w.setFlintModel(None)
            w.setScan(None)
            w.setObjectName(None)
            w.deleteLater()

    def __getSettings(self) -> HashObjSetting:
        """Returns the settings storing workspaces in this bliss session."""
        flintModel = self.mainManager().flintModel()
        redis = flintModel.redisConnection()
        key = self.ROOT_KEY % flintModel.blissSessionName()
        setting = HashObjSetting(key, connection=redis)
        return setting

    def __reloadLayout(self):
        flintModel = self.mainManager().flintModel()
        name = self.__getLastWorkspaceName()
        window = flintModel.liveWindow()
        settings = self.__getSettings()

        try:
            data = settings.get(name, None)
        except:
            _logger.error(
                "Problem to load workspace data. Information will be lost.",
                exc_info=True,
            )
            data = None

        if data is not None and not isinstance(data, WorkspaceData):
            _logger.error(
                "Problem to load workspace data. Unexpected type %s. Information will be lost.",
                type(data),
                exc_info=True,
            )
            data = None

        if data is None:
            return

        layout = data.layout()
        window.restoreState(layout)

    def loadWorkspace(self, name: str):
        flintModel = self.mainManager().flintModel()
        newWorkspace = flint_model.Workspace()
        newWorkspace.setName(name)
        window = flintModel.liveWindow()
        settings = self.__getSettings()
        scan = flintModel.currentScan()

        try:
            data = settings.get(newWorkspace.name(), None)
        except:
            _logger.error(
                "Problem to load workspace data. Information will be lost.",
                exc_info=True,
            )
            data = None

        if data is not None and not isinstance(data, WorkspaceData):
            _logger.error(
                "Problem to load workspace data. Unexpected type %s. Information will be lost.",
                type(data),
                exc_info=True,
            )
            data = None

        if data is None:
            window.feedDefaultWorkspace(flintModel, newWorkspace)
        else:
            # It have to be done before creating widgets
            self.__closeWorkspace()

            data.feedWorkspace(newWorkspace, parent=window)

            # FIXME: Could be done in the manager callback event
            for plot in newWorkspace.plots():
                # FIXME: That's a hack while there is no better solution
                style = plot.styleStrategy()
                if hasattr(style, "setFlintModel"):
                    style.setFlintModel(flintModel)

            # FIXME: Could be done in the manager callback event
            for widget in newWorkspace.widgets():
                self.parent()._initNewDock(widget)
                widget.setScan(scan)

            layout = data.layout()
            window.restoreState(layout)

        # Make sure everything is visible (just in case)
        for widget in newWorkspace.widgets():
            widget.setVisible(True)

        self.__saveCurrentWorkspaceName(newWorkspace.name())
        flintModel.setWorkspace(newWorkspace)

    def removeWorkspace(self, name: str):
        names = self.__getAvailableNames()
        if name in names:
            names.remove(name)
        self.__saveAvailableNames(names)

        key = "flint.workspace.%s" % name
        flintModel = self.mainManager().flintModel()
        redis = flintModel.redisConnection()
        redis.delete(key)

    def switchToWorkspace(self, name: str):
        """Save the current workspace the load the requested one"""
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        self.saveWorkspace(workspace)
        self.loadWorkspace(name)

    def saveWorkspace(self, workspace: flint_model.Workspace, last=False):
        """Save this workspace

        Arguments:
            - last: If true, save that this workspace was used
        """
        name = workspace.name()
        names = self.__getAvailableNames()
        if name not in names:
            names.append(name)
            self.__saveAvailableNames(names)

        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()

        redis = flintModel.redisConnection()
        if redis is None:
            _logger.error("No Redis connection. Save of workspace aborted")
            return

        data = WorkspaceData()
        includePlots = workspace.name() != self.DEFAULT
        data.setWorkspace(workspace, includePlots=includePlots)

        window = flintModel.liveWindow()
        layout = window.saveState()
        data.setLayout(layout)

        settings = self.__getSettings()
        settings[name] = data

        if last:
            self.__saveCurrentWorkspaceName(name)

    def saveWorkspaceAs(self, workspace: flint_model.Workspace, name: str):
        previous = workspace.name()
        if previous == name:
            return
        workspace.setName(name)
        self.saveWorkspace(workspace, last=True)
        flintModel = self.mainManager().flintModel()
        flintModel.setWorkspace(workspace)

    def renameWorkspaceAs(self, workspace: flint_model.Workspace, name: str):
        previous = workspace.name()
        if previous == name:
            return
        workspace.setName(name)
        self.removeWorkspace(previous)
        self.saveWorkspace(workspace, last=True)
        flintModel = self.mainManager().flintModel()
        flintModel.setWorkspace(workspace)
