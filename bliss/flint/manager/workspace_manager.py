# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
from silx.gui.qt import inspect

from bliss.config.settings import HashObjSetting
from . import manager
from ..model import flint_model
from bliss.flint import config
from bliss.flint.widgets.utils.plot_helper import PlotWidget


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
    def setWorkspace(
        self, workspace: flint_model.Workspace, includePlots: bool = False
    ):
        plots = {}
        if includePlots:
            for plot in workspace.plots():
                plots[id(plot)] = plot

        widgetDescriptions = []
        for widget in workspace.widgets():

            if not inspect.isValid(widget):
                continue

            if includePlots and isinstance(widget, PlotWidget):
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

    def widgetDescriptions(self) -> List[WidgetDescription]:
        return self["widgets"]

    def setLiveWindow(self, window: qt.QWidget):
        config = window.configuration()
        self["layout"] = window.saveState()
        self["window_config"] = config

    def initLiveWindow(self, window: qt.QWidget, workspace: flint_model.Workspace):

        # FIXME ugly hack to reach new widgets created by live window
        model = window.flintModel()
        currentWorkspace = model.workspace()
        if currentWorkspace is not None:
            previousWidgets = set(currentWorkspace.widgets())
        else:
            previousWidgets = set()

        window.updateFromWorkspace(workspace)
        if "window_config" in self:
            config = self["window_config"]
            window.setConfiguration(config)

        # FIXME ugly hack to reach new widgets created by live window
        if currentWorkspace is not None:
            currentWidgets = set(currentWorkspace.widgets())
        else:
            currentWidgets = set()

        newWidgets = currentWidgets - previousWidgets
        for widget in newWidgets:
            workspace.addWidget(widget)

        layout = self["layout"]
        _logger.debug("Restore layout state")
        window.restoreState(layout)

    def feedWorkspace(
        self,
        workspace: flint_model.Workspace,
        remainingWidgets: List[qt.QWidget],
        parent: qt.QMainWindow,
    ):
        plots: dict = self["plots"]
        widgetDescriptions = self["widgets"]

        descriptions = []
        for data in widgetDescriptions:
            if isinstance(data, tuple):
                data = _WidgetDescriptionCompatibility(*data, None)
            descriptions.append(data)

        objectNames = set([d.objectName for d in descriptions])

        existingWidgets = {w.objectName(): w for w in remainingWidgets}

        def pickUnusedObjectName():
            for i in range(100):
                name = "dock-%01d" % i
                if name not in objectNames:
                    objectNames.add(name)
                    return name
            return "dock-666-666"

        for data in descriptions:

            if data.objectName is None or data.objectName == "":
                _logger.warning(
                    "Widget %s from workspace configuration have no name. Generate one.",
                    data.className,
                )
                objectName = pickUnusedObjectName()
            else:
                objectName = data.objectName

            if objectName in existingWidgets:
                widget = existingWidgets[objectName]
                if parent is not None:
                    widget.setParent(parent)
            else:
                widget = data.className(parent)
            widget.setObjectName(objectName)
            widget.setWindowTitle(data.windowTitle)
            if hasattr(widget, "setConfiguration") and data.config is not None:
                widget.setConfiguration(data.config)

            # Looks needed to retrieve the right layout with restoreSate
            if parent is not None:
                parent.addDockWidget(qt.Qt.LeftDockWidgetArea, widget)
            if objectName not in existingWidgets:
                if data.modelId is not None:
                    plot = plots[data.modelId]
                    widget.setPlotModel(plot)
            workspace.addWidget(widget)


class WorkspaceManager(qt.QObject):

    DEFAULT = "base"

    def __init__(self, parent=None):
        qt.QObject.__init__(self, parent=parent)
        self.__session: Dict[str, WorkspaceData] = {}
        """Save workspace during flint life time"""

    def mainManager(self) -> manager.ManageMainBehaviours:
        return self.parent()

    def connectManagerActions(self, parent: qt.QObject, menu: qt.QMenu):
        """Create actions to interact with the manager"""
        menu.aboutToShow.connect(self.__feedWorkspaceMenu)

    def __feedWorkspaceMenu(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        currentWorkspace = workspace.name()

        try:
            names = self.__getAvailableNames()
        except IOError:
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText("Error while loading names")
            menu.addAction(action)
            names = []

        names = list(sorted(names))

        menu.addSection("Active workspace")
        group = qt.QActionGroup(menu)
        if len(names) > 0:
            for name in names:
                action = qt.QAction(menu)
                action.setText(f"{name}")
                action.setCheckable(True)
                if name == currentWorkspace:
                    action.setToolTip("The current workspace")
                    action.setChecked(True)
                    action.setEnabled(False)
                else:
                    action.triggered.connect(
                        functools.partial(self.switchToWorkspace, name)
                    )
                    action.setToolTip("Switch to '%s' workspace" % name)
                menu.addAction(action)
                group.addAction(action)
        else:
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText("No workspace")
            menu.addAction(action)

        menu.addSeparator()

        action = qt.QAction(menu)
        action.setText("Reload")
        action.setToolTip("Reload the last saved state of the active workspace")
        action.triggered.connect(self.reloadCurrentWorkspace)
        iconName = qt.QStyle.SP_FileDialogBack
        icon = menu.style().standardIcon(iconName)
        action.setIcon(icon)
        menu.addAction(action)

        action = qt.QAction(menu)
        action.setText("Save")
        action.setToolTip("Save the active workspace")
        action.triggered.connect(self.saveCurrentWorkspace)
        menu.addAction(action)

        action = qt.QAction(menu)
        action.setText("Save as...")
        action.setToolTip("Save the active workspace into another name")
        action.triggered.connect(self.saveCurrentWorkspaceAs)
        menu.addAction(action)

        action = qt.QAction(menu)
        action.setText("Rename as...")
        action.setToolTip("Rename the active workspace to another name")
        action.triggered.connect(self.renameCurrentWorkspaceAs)
        menu.addAction(action)

        action = qt.QAction(menu)
        action.setText("Remove")
        action.setToolTip(
            "Remove the active workspace (after switching to the default workspace)"
        )
        action.triggered.connect(
            functools.partial(self.removeWorkspace, currentWorkspace)
        )
        icon = icons.getQIcon("flint:icons/remove-item")
        action.setIcon(icon)
        menu.addAction(action)

    def __saveAvailableNames(self, names: List[str]):
        settings = self.__getSettings()
        settings["@names"] = names

    def __getAvailableNames(self) -> List[str]:
        settings = self.__getSettings()
        names = settings.get("@names", [])
        return names

    def renameCurrentWorkspaceAs(self):
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

    def saveCurrentWorkspaceAs(self):
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
        settings = self.__getSessionSettings()
        settings["@lastname"] = name

    def __getLastWorkspaceName(self):
        settings = self.__getSessionSettings()
        name = settings.get("@lastname", self.DEFAULT)
        return name

    def loadLastWorkspace(self):
        try:
            name = self.__getLastWorkspaceName()
        except ValueError:
            name = self.DEFAULT
        return self.loadWorkspace(name)

    def __closeWorkspace(self):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        if workspace is None:
            return
        widgets = workspace.popWidgets()
        for w in widgets:
            # Make sure we can create object name without collision
            if isinstance(w, PlotWidget):
                w.setPlotModel(None)
                w.setScan(None)
            if hasattr(w, "setFlintModel"):
                w.setFlintModel(None)
            w.setObjectName(None)
            w.deleteLater()

    def __closeUnusedWidget(self, data: WorkspaceData):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        if workspace is None:
            return
        widgets = workspace.popWidgets()
        names = set([desc.objectName for desc in data.widgetDescriptions()])
        for w in list(widgets):
            if w.objectName() in names:
                continue
            # Make sure we can create object name without collision
            widgets.remove(w)
            if isinstance(w, PlotWidget):
                w.setPlotModel(None)
                w.setScan(None)
            if hasattr(w, "setFlintModel"):
                w.setFlintModel(None)
            w.setObjectName(None)
            w.deleteLater()
        return widgets

    def __getSessionSettings(self) -> HashObjSetting:
        """Returns the settings storing workspaces in this bliss session."""
        flintModel = self.mainManager().flintModel()
        redis = flintModel.redisConnection()
        sessionName = flintModel.blissSessionName()
        if sessionName is None:
            raise ValueError("No session defined")

        key = config.get_workspace_key(sessionName)
        setting = HashObjSetting(key, connection=redis)

        return setting

    def __getSettings(self) -> HashObjSetting:
        """Returns the settings storing workspaces in this bliss session."""
        flintModel = self.mainManager().flintModel()
        redis = flintModel.redisConnection()
        sessionName = flintModel.blissSessionName()
        if sessionName is None:
            raise ValueError("No session defined")

        key = config.get_workspace_key(None)
        setting = HashObjSetting(key, connection=redis)

        if len(setting) == 0:
            # FIXME: Move settings from BLISS <= 1.7dev to BLISS 1.7
            key = config.get_workspace_key(sessionName)
            oldSetting = HashObjSetting(key, connection=redis)
            setting.update(oldSetting.get_all())

        return setting

    def reloadCurrentWorkspace(self):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        name = workspace.name()
        self.loadWorkspace(name, flintScope=False)

    def loadWorkspace(self, name: str, flintScope: bool = True):
        _logger.debug("Load workspace %s", name)
        flintModel = self.mainManager().flintModel()

        newWorkspace = flint_model.Workspace()
        newWorkspace.setName(name)
        window = flintModel.liveWindow()
        scan = flintModel.currentScan()

        data = None

        sessionName = flintModel.blissSessionName()

        if flintScope:
            if name in self.__session:
                data = self.__session[name]
        else:
            if name in self.__session:
                del self.__session[name]

        if data is None:
            if sessionName is not None:
                try:
                    settings = self.__getSettings()
                    data = settings.get(newWorkspace.name(), None)
                except Exception:
                    _logger.error(
                        "Problem to load workspace data. Information will be lost.",
                        exc_info=True,
                    )

        if data is not None and not isinstance(data, WorkspaceData):
            _logger.error(
                "Problem to load workspace data. Unexpected type %s. Information will be lost.",
                type(data),
                exc_info=True,
            )
            data = None

        if data is None:
            # It have to be done before creating widgets
            self.__closeWorkspace()
            window.feedDefaultWorkspace(flintModel, newWorkspace)
        else:
            # It have to be done before creating widgets
            remainingWidgets = self.__closeUnusedWidget(data)
            flintModel = self.mainManager().flintModel()
            data.feedWorkspace(
                newWorkspace, remainingWidgets=remainingWidgets, parent=window
            )

            # FIXME: Could be done in the manager callback event
            for plot in newWorkspace.plots():
                # FIXME: That's a hack while there is no better solution
                style = plot.styleStrategy()
                if hasattr(style, "setFlintModel"):
                    style.setFlintModel(flintModel)

            # FIXME: Could be done in the manager callback event
            for widget in newWorkspace.widgets():
                self.parent()._initNewDock(widget)
                if isinstance(widget, PlotWidget):
                    widget.setScan(scan)

            data.initLiveWindow(window, newWorkspace)

        # Make sure everything is visible (just in case)
        for widget in newWorkspace.widgets():
            widget.setVisible(True)

        if sessionName is not None:
            self.__saveCurrentWorkspaceName(newWorkspace.name())

        flintModel.setWorkspace(newWorkspace)

    def removeWorkspace(self, name: str):
        if name == self.DEFAULT:
            _logger.warning("The base workspace can't be removed", self.DEFAULT)
            return

        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        currentWorkspace = workspace.name()
        if name == currentWorkspace:
            _logger.info(
                "Switch to '%s' workspace before removing '%s'", self.DEFAULT, name
            )
            self.loadWorkspace(self.DEFAULT)

        names = self.__getAvailableNames()
        if name in names:
            names.remove(name)
        self.__saveAvailableNames(names)

        if name in self.__session:
            del self.__session[name]

        key = "flint.workspace.%s" % name
        flintModel = self.mainManager().flintModel()
        redis = flintModel.redisConnection()
        redis.delete(key)

    def switchToWorkspace(self, name: str):
        """Save the current workspace the load the requested one"""
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        self.saveWorkspace(workspace, flintScope=True)
        self.loadWorkspace(name)

    def saveCurrentWorkspace(self):
        flintModel = self.mainManager().flintModel()
        workspace = flintModel.workspace()
        self.saveWorkspace(workspace, flintScope=False)

    def saveWorkspace(
        self, workspace: flint_model.Workspace, last=False, flintScope: bool = False
    ):
        """Save this workspace

        Arguments:
            - last: If true, save that this workspace was used
            - flintScope: If true, the workspace is save at flint scope, else
                the flint scope is cleaned up and the workspace is saved in
                Redis
        """
        flintModel = self.mainManager().flintModel()
        sessionName = flintModel.blissSessionName()
        if sessionName is None:
            _logger.error("No BLISS session. Save of workspace aborted")
            return

        name = workspace.name()
        names = self.__getAvailableNames()
        if name not in names:
            names.append(name)
            self.__saveAvailableNames(names)

        workspace = flintModel.workspace()

        redis = flintModel.redisConnection()
        if redis is None:
            _logger.error("No Redis connection. Save of workspace aborted")
            return

        data = WorkspaceData()
        window = flintModel.liveWindow()
        data.setWorkspace(workspace)

        data.setLiveWindow(window)

        if flintScope:
            self.__session[name] = data
        else:
            if name in self.__session:
                del self.__session[name]
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
