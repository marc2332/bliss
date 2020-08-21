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
from typing import Optional
from typing import List
from typing import ClassVar

import gevent.event
from bliss.config.conductor.client import get_default_connection
from bliss.config.conductor.client import get_redis_connection
from bliss.flint import config

import logging
from silx.gui import qt
from tango.gevent import DeviceProxy

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.helper import model_helper
from bliss.flint.helper.style_helper import DefaultStyleStrategy
from bliss.flint.widgets.utils.plot_helper import PlotWidget

from ..helper import scan_info_helper
from . import workspace_manager
from . import monitoring

_logger = logging.getLogger(__name__)


class ManageMainBehaviours(qt.QObject):
    def __init__(self, parent=None):
        super(ManageMainBehaviours, self).__init__(parent=parent)
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__activeDock = None
        self.__classMapping = {}
        self.__flintStarted = gevent.event.Event()
        self.__flintStarted.clear()
        self.__workspaceManager = workspace_manager.WorkspaceManager(self)
        self.__tangoMetadata = None

    def setFlintModel(self, flintModel: flint_model.FlintState):
        if self.__flintModel is not None:
            self.__flintModel.workspaceChanged.disconnect(self.__workspaceChanged)
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
            self.__flintModel.aliveScanAdded.disconnect(self.__aliveScanDiscovered)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.workspaceChanged.connect(self.__workspaceChanged)
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)
            self.__flintModel.aliveScanAdded.connect(self.__aliveScanDiscovered)

    def setTangoMetadataName(self, name: str):
        if name in [None, ""]:
            device = None
        else:
            device = DeviceProxy(name)
        self.__flintModel.setTangoMetadata(device)

    def flintModel(self) -> flint_model.FlintState:
        flintModel = self.__flintModel
        assert flintModel is not None
        return flintModel

    def initRedis(self):
        connection = get_default_connection()
        redisConnection = connection.get_redis_connection()
        flintModel = self.flintModel()
        flintModel.setRedisConnection(redisConnection)
        try:
            # NOTE: Here the session can not yet be defined
            self.workspaceManager().loadLastWorkspace()
        except Exception:
            _logger.error("Error while loading the workspace", exc_info=True)

    def updateBlissSessionName(self, sessionName):
        flintModel = self.flintModel()
        previousSessionName = flintModel.blissSessionName()
        if previousSessionName == sessionName:
            # FIXME: In case of a restart of bliss, is it safe?
            return False

        redis = get_redis_connection()
        key = config.get_flint_key()
        current_value = redis.lindex(key, 0).decode()
        value = sessionName + " " + current_value.split()[-1]
        redis.lpush(key, value)
        redis.rpop(key)
        flintModel.setBlissSessionName(sessionName)
        self.workspaceManager().loadLastWorkspace()
        return True

    def __workspaceChanged(
        self,
        previousWorkspace: flint_model.Workspace,
        newWorkspace: flint_model.Workspace,
    ):
        if self.__flintModel is None:
            return
        scan = self.__flintModel.currentScan()
        if scan is not None:
            self.__storeScanIfNeeded(scan)

        if previousWorkspace is not None:
            for widget in previousWorkspace.widgets():
                self.__widgetRemoved(widget)
            previousWorkspace.widgetAdded.disconnect(self.__widgetAdded)
            previousWorkspace.widgetRemoved.disconnect(self.__widgetRemoved)
        if newWorkspace is not None:
            for widget in newWorkspace.widgets():
                self.__widgetAdded(widget)
            newWorkspace.widgetAdded.connect(self.__widgetAdded)
            newWorkspace.widgetRemoved.connect(self.__widgetRemoved)

            for widget in newWorkspace.widgets():
                if widget.isVisible():
                    widget.widgetActivated.emit(widget)
                    break
        self.__updateLiveScanTitle()

    def __widgetAdded(self, widget):
        widget.widgetActivated.connect(self.__widgetActivated)

    def __widgetRemoved(self, widget):
        widget.widgetActivated.disconnect(self.__widgetActivated)

    def __widgetActivated(self, widget):
        if self.__activeDock is widget:
            # Filter double selection
            return
        self.__activeDock = widget

        if hasattr(widget, "createPropertyWidget"):
            flintModel = self.flintModel()
            liveWindow = flintModel.liveWindow()
            propertyWidget = liveWindow.propertyWidget()
            if propertyWidget is not None:
                propertyWidget.setFocusWidget(widget)

    def __currentScanChanged(self, previousScan, newScan):
        self.__storeScanIfNeeded(newScan)

    def __updateLiveScanTitle(self):
        window = self.flintModel().liveWindow()
        # FIXME: Not nice to reach the tabWidget. It is implementation dependent
        tabWidget: qt.QTabWidget = window.parent().parent()
        liveScanIndex = tabWidget.indexOf(window)
        tabWidget.setCurrentIndex(liveScanIndex)

        flintModel = self.flintModel()
        workspace = flintModel.workspace()
        if workspace is not None:
            workspaceName = workspace.name()
        else:
            workspaceName = None

        title = ""
        if workspaceName is not None:
            title += f"({workspaceName}) "
        title += "Live scan"

        tabWidget.setTabText(liveScanIndex, title)

    def __storeScanIfNeeded(self, scan: scan_model.Scan):
        flintModel = self.__flintModel
        if flintModel is None:
            return None
        workspace = flintModel.workspace()
        if workspace is None:
            return None
        for plot in workspace.plots():
            if isinstance(plot, plot_item_model.CurvePlot):
                if plot.isScansStored():
                    item = plot_item_model.ScanItem(plot, scan)
                    plot.addItem(item)

    def saveBeforeClosing(self):
        flintModel = self.flintModel()
        workspace = flintModel.workspace()
        self.workspaceManager().saveWorkspace(workspace, last=True)
        _logger.info("Workspace saved")

    def _initNewDock(self, widget):
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(self.__flintModel)
        widget.windowClosed.connect(self.__dockClosed)

    def __initClassMapping(self):
        if len(self.__classMapping) > 0:
            return
        from bliss.flint.widgets.curve_plot import CurvePlotWidget
        from bliss.flint.widgets.mca_plot import McaPlotWidget
        from bliss.flint.widgets.image_plot import ImagePlotWidget
        from bliss.flint.widgets.scatter_plot import ScatterPlotWidget

        mapping = [
            (CurvePlotWidget, plot_item_model.CurvePlot),
            (McaPlotWidget, plot_item_model.McaPlot),
            (ImagePlotWidget, plot_item_model.ImagePlot),
            (ScatterPlotWidget, plot_item_model.ScatterPlot),
        ]

        for k, v in mapping:
            self.__classMapping[k] = v
            self.__classMapping[v] = k

    def __getWidgetClassFromPlotClass(
        self, plotClass: ClassVar[plot_model.Plot]
    ) -> ClassVar[qt.QDockWidget]:
        self.__initClassMapping()
        return self.__classMapping.get(plotClass, None)

    def __getPlotClassFromWidgetClass(
        self, widgetClass: ClassVar[qt.QDockWidget]
    ) -> ClassVar[plot_model.Plot]:
        self.__initClassMapping()
        return self.__classMapping.get(widgetClass, None)

    def moveWidgetToWorkspace(self, workspace):
        flintModel = self.flintModel()
        widgets = flintModel.workspace().popWidgets()
        availablePlots = list(workspace.plots())
        for widget in widgets:
            widget.setFlintModel(self.__flintModel)

            compatibleModel = self.__getPlotClassFromWidgetClass(type(widget))
            if compatibleModel is None:
                _logger.error("No compatible class model")
                plotModel = None
            else:
                plots = [p for p in availablePlots if isinstance(p, compatibleModel)]
                if len(plots) > 0:
                    plotModel = plots[0]
                    availablePlots.remove(plotModel)
                else:
                    _logger.error("No compatible model")
                    plotModel = compatibleModel()
                    plotModel.setStyleStrategy(DefaultStyleStrategy(self.__flintModel))

            widget.setPlotModel(plotModel)
            workspace.addWidget(widget)

    def __aliveScanDiscovered(self, scan):
        currentScan = self.flintModel().currentScan()
        if (
            currentScan is not None
            and currentScan.state() != scan_model.ScanState.FINISHED
        ):
            return

        if isinstance(scan, scan_model.ScanGroup):
            # Skip groups without plots
            if not scan.hasPlotDescription():
                return

        # Update the current scan only if the previous one is finished
        # FIXME: It should be managed in a better way, but for now it's fine
        scanInfo = scan.scanInfo()
        plots = scan_info_helper.create_plot_model(scanInfo, scan)
        self.updateScanAndPlots(scan, plots)

    def __clearPreviousScan(self, scan):
        if isinstance(scan, monitoring.MonitoringScan):
            if scan.isMonitoring():
                scan.stopMonitoring()

    def __getCompatiblePlots(self, widget, availablePlots) -> List[plot_model.Plot]:
        compatibleModel = self.__getPlotClassFromWidgetClass(type(widget))
        if compatibleModel is None:
            return []
        plots = [p for p in availablePlots if isinstance(p, compatibleModel)]
        windowTitle = widget.windowTitle()
        if issubclass(
            compatibleModel, (plot_item_model.ImagePlot, plot_item_model.McaPlot)
        ):
            # FIXME: windowTitle should not be used, but for now it is convenient
            plots = [p for p in plots if p.deviceName() == windowTitle]
        # plot with names will use dedicated widgets
        plots = [p for p in plots if p.name() is None or p.name() == windowTitle]
        return plots

    def updateScanAndPlots(self, scan: scan_model.Scan, plots: List[plot_model.Plot]):
        flintModel = self.flintModel()
        liveWindow = flintModel.liveWindow()
        previousScan = flintModel.currentScan()
        if previousScan is not None:
            useDefaultPlot = (
                scan.scanInfo()
                .get("_display_extra", {})
                .get("displayed_channels", None)
                is not None
            )
        else:
            useDefaultPlot = True

        if len(plots) > 0:
            defaultPlot = plots[0]
        else:
            defaultPlot = None

        isCt = scan.type() == "ct"
        if isCt:
            # Filter out curves and scatters
            plots = [
                p
                for p in plots
                if isinstance(p, (plot_item_model.ImagePlot, plot_item_model.McaPlot))
            ]
            # FIXME: If we remove image and MCAs, there is maybe nothing to display
            ctWidget = liveWindow.ctWidget()
            ctWidget.setScan(scan)
            ctWidget.show()
            ctWidget.raise_()
            ctWidget.setFocus(qt.Qt.OtherFocusReason)

        # Set the new scan
        flintModel.setCurrentScan(scan)

        # Reuse/create and connect the widgets
        self.updateWidgetsWithPlots(scan, plots, useDefaultPlot, defaultPlot)

    def updateWidgetsWithPlots(self, scan, plots, useDefaultPlot, defaultPlot):
        """Update the widgets with a set of plots"""
        flintModel = self.flintModel()
        workspace = flintModel.workspace()
        availablePlots = list(plots)
        widgets = flintModel.workspace().widgets()
        defaultWidget = None
        for widget in widgets:
            plots = self.__getCompatiblePlots(widget, availablePlots)
            if len(plots) == 0:
                # Do not update the widget (scan and plot stays as previous state)
                continue

            plotModel = plots[0]
            availablePlots.remove(plotModel)
            previousWidgetPlot = widget.plotModel()
            if plotModel is defaultPlot:
                defaultWidget = widget

            # Try to reuse the previous plot
            if not useDefaultPlot and previousWidgetPlot is not None:
                with previousWidgetPlot.transaction():
                    # Clean up temporary items
                    for item in list(previousWidgetPlot.items()):
                        if isinstance(item, plot_model.NotReused):
                            try:
                                previousWidgetPlot.removeItem(item)
                            except Exception:
                                pass

                    # Reuse only available values
                    # FIXME: Make it work first for curves, that's the main use case
                    if isinstance(previousWidgetPlot, plot_item_model.CurvePlot):
                        model_helper.removeNotAvailableChannels(
                            previousWidgetPlot, plotModel, scan
                        )

            if (
                useDefaultPlot
                or previousWidgetPlot is None
                or previousWidgetPlot.isEmpty()
            ):
                if plotModel.styleStrategy() is None:
                    plotModel.setStyleStrategy(DefaultStyleStrategy(self.__flintModel))
                widget.setPlotModel(plotModel)

            previousScan = widget.scan()
            self.__clearPreviousScan(previousScan)
            widget.setScan(scan)

        # There is no way in Qt to tabify a widget to a new floating widget
        # Then this code tabify the new widgets on an existing widget
        # FIXME: This behavior is not really convenient
        widgets = workspace.widgets()
        if len(widgets) == 0:
            lastTab = None
        else:
            lastTab = widgets[0]

        # Create widgets for unused plots
        window = flintModel.liveWindow()
        for plotModel in availablePlots:
            if plotModel.styleStrategy() is None:
                plotModel.setStyleStrategy(DefaultStyleStrategy(flintModel))
            widget = self.__createWidgetFromPlot(window, plotModel)
            if widget is None:
                continue
            if plotModel is defaultPlot:
                defaultWidget = widget

            workspace.addWidget(widget)
            previousScan = widget.scan()
            self.__clearPreviousScan(previousScan)
            widget.setScan(scan)

            if lastTab is None:
                window.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
                widget.setVisible(True)
            else:
                window.tabifyDockWidget(lastTab, widget)
            lastTab = widget

        if defaultWidget is not None:
            # Try to set the focus on the default plot
            defaultWidget.show()
            defaultWidget.raise_()
            defaultWidget.setFocus(qt.Qt.OtherFocusReason)
            self.__widgetActivated(defaultWidget)

    def __dockClosed(self):
        dock = self.sender()
        flintModel = self.flintModel()
        liveWindow = flintModel.liveWindow()
        propertyWidget = liveWindow.propertyWidget()
        if propertyWidget.focusWidget() is dock:
            propertyWidget.setFocusWidget(None)

        if isinstance(dock, PlotWidget):
            dock.setPlotModel(None)
        dock.setFlintModel(None)
        workspace = flintModel.workspace()
        workspace.removeWidget(dock)

    def __createWidgetFromPlot(
        self, parent: qt.QWidget, plotModel: plot_model.Plot
    ) -> qt.QDockWidget:
        widgetClass = self.__getWidgetClassFromPlotClass(type(plotModel))
        if widgetClass is None:
            _logger.error(
                "No compatible widget for plot model %s. Plot not displayed.",
                type(plotModel),
            )
            return None

        flintModel = self.flintModel()
        workspace = flintModel.workspace()
        widget: qt.QDockWidget = widgetClass(parent)
        widget.setPlotModel(plotModel)
        self._initNewDock(widget)

        title = plotModel.name()
        if title is None:
            if isinstance(
                plotModel, (plot_item_model.ImagePlot, plot_item_model.McaPlot)
            ):
                title = plotModel.deviceName()
            else:
                prefix = str(widgetClass.__name__).replace("PlotWidget", "")
                title = self.__getUnusedTitle(prefix, workspace)

        name = type(plotModel).__name__ + "-" + title
        name = name.replace(":", "--")
        name = name.replace(".", "--")
        name = name.replace(" ", "--")
        name = name.lower() + "-dock"

        widget.setWindowTitle(title)
        widget.setObjectName(name)
        return widget

    def __getUnusedTitle(self, prefix, workspace) -> str:
        for num in range(1, 100):
            title = prefix + str(num)
            for widget in workspace.widgets():
                if widget.windowTitle() == title:
                    break
            else:
                return title
        return title

    def allocateProfileDock(self):
        from bliss.flint.widgets import holder_widget

        flintModel = self.flintModel()
        workspace = flintModel.workspace()

        # Search for an existing profile
        otherProfiles = [
            w
            for w in workspace.widgets()
            if isinstance(w, holder_widget.ProfileHolderWidget)
        ]
        for w in otherProfiles:
            if w.isUsed():
                continue
            w.setVisible(True)
            w.setUsed(True)
            return w

        # Create the profile widget
        window = flintModel.liveWindow()
        widget = holder_widget.ProfileHolderWidget(parent=window)
        self._initNewDock(widget)
        workspace.addWidget(widget)

        # Search for another profile
        lastTab = None if len(otherProfiles) == 0 else otherProfiles[-1]

        def findFreeName(widget, template, others):
            for i in range(1, 100):
                name = template % i
                for w in others:
                    if w.objectName() == name:
                        break
                else:
                    return name
            # That's a dup name
            return template % abs(id(widget))

        widget.setVisible(True)
        name = findFreeName(widget, "profile-%s", otherProfiles)
        widget.setObjectName(name)
        widget.setWindowTitle(name.capitalize().replace("-", " "))
        widget.setUsed(True)

        if lastTab is not None:
            window.tabifyDockWidget(lastTab, widget)
        else:
            window.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
            widget.setFloating(True)
        return widget

    def setFlintStarted(self):
        self.__flintStarted.set()

    def waitFlintStarted(self):
        self.__flintStarted.wait()

    def workspaceManager(self) -> workspace_manager.WorkspaceManager:
        return self.__workspaceManager
