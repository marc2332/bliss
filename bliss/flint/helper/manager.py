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
from typing import Optional
from typing import List
from typing import Dict
from typing import ClassVar

import pickle
import logging
from silx.gui import qt

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.helper import model_helper
from bliss.flint.helper.style_helper import DefaultStyleStrategy

_logger = logging.getLogger(__name__)


class ManageMainBehaviours(qt.QObject):
    def __init__(self, parent=None):
        super(ManageMainBehaviours, self).__init__(parent=parent)
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__activeDock = None
        self.__classMapping = {}

    def setFlintModel(self, flintModel: flint_model.FlintState):
        if self.__flintModel is not None:
            self.__flintModel.workspaceChanged.disconnect(self.__workspaceChanged)
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.workspaceChanged.connect(self.__workspaceChanged)
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)

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

    def __widgetAdded(self, widget):
        widget.widgetActivated.connect(self.__widgetActivated)

    def __widgetRemoved(self, widget):
        widget.widgetActivated.disconnect(self.__widgetActivated)

    def __widgetActivated(self, widget):
        if self.__activeDock is widget:
            # Filter double selection
            return
        self.__activeDock = widget

        propertyWidget = self.__flintModel.propertyWidget()
        if propertyWidget is not None:
            propertyWidget.setFocusWidget(widget)

    def __currentScanChanged(self, previousScan, newScan):
        self.__storeScanIfNeeded(newScan)
        self.__updateLiveScanWindow(newScan)

    def __updateLiveScanWindow(self, newScan: scan_model.Scan):
        window = self.__flintModel.liveWindow()
        # FIXME: Not nice to reach the tabWidget. It is implementation dependent
        tabWidget: qt.QTabWidget = window.parent().parent()
        liveScanIndex = tabWidget.indexOf(window)
        tabWidget.setCurrentIndex(liveScanIndex)

        scan_info = newScan.scanInfo()
        title = scan_info["title"]
        scan_nb = scan_info["scan_nb"]

        text = f"Live scan | {title} - scan number {scan_nb}"
        tabWidget.setTabText(liveScanIndex, text)

    def __storeScanIfNeeded(self, scan: scan_model.Scan):
        if self.__flintModel is None:
            return None
        workspace = self.__flintModel.workspace()
        if workspace is None:
            return None
        for plot in workspace.plots():
            if isinstance(plot, plot_item_model.CurvePlot):
                if plot.isScansStored():
                    item = plot_item_model.ScanItem(plot, scan)
                    plot.addItem(item)

    def saveWorkspace(self, includePlots=True):
        workspace = self.__flintModel.workspace()
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
            widgetDescriptions.append(
                (widget.objectName(), widget.windowTitle(), widget.__class__, modelId)
            )

        window = self.__flintModel.liveWindow()
        layout = window.saveState()

        state = (plots, widgetDescriptions, layout)
        return pickle.dumps(state)

    def closeWorkspace(self):
        workspace = self.__flintModel.workspace()
        widgets = workspace.popWidgets()
        for w in widgets:
            # Make sure we can create object name without collision
            w.setPlotModel(None)
            w.setFlintModel(None)
            w.setObjectName(None)
            w.deleteLater()

    def restoreWorkspace(self, state):
        plots, widgetDescriptions, layout = pickle.loads(state)

        # It have to be done before creating widgets
        self.closeWorkspace()

        workspace = flint_model.Workspace()

        for plot in plots.values():
            workspace.addPlot(plot)

        window = self.__flintModel.liveWindow()
        for name, title, widgetClass, modelId in widgetDescriptions:
            widget = widgetClass(window)
            widget.setObjectName(name)
            widget.setWindowTitle(title)
            self.__initNewDock(widget)
            if modelId is not None:
                plot = plots[modelId]
                widget.setPlotModel(plot)
            workspace.addWidget(widget)

        window.restoreState(layout)

        # Make sure everything is visible (just in case)
        for widget in workspace.widgets():
            widget.setVisible(True)

        self.__flintModel.setWorkspace(workspace)

    def __initNewDock(self, widget):
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
        widgets = self.__flintModel.workspace().popWidgets()
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
                    plotModel.setStyleStrategy(DefaultStyleStrategy())
                    workspace.addPlot(plotModel)

            widget.setPlotModel(plotModel)
            workspace.addWidget(widget)

    def updateScanAndPlots(self, scan: scan_model.Scan, plots: List[plot_model.Plot]):
        flint = self.__flintModel
        workspace = flint.workspace()

        if flint.currentScan() is not None:
            sameScan = (
                flint.currentScan().scanInfo()["acquisition_chain"]
                == scan.scanInfo()["acquisition_chain"]
            )
        else:
            sameScan = False

        isCt = scan.scanInfo().get("type", None) == "ct"
        if isCt:
            # Filter out curves and scatters
            plots = [
                p
                for p in plots
                if isinstance(p, (plot_item_model.ImagePlot, plot_item_model.McaPlot))
            ]

        # Remove previous plot models
        if not sameScan and not isCt:
            for widget in workspace.widgets():
                widget.setPlotModel(None)
            for plot in workspace.plots():
                workspace.removePlot(plot)

        # Set the new scan
        flint.setCurrentScan(scan)

        # Reuse/create and connect the widgets
        availablePlots = list(plots)
        widgets = self.__flintModel.workspace().widgets()
        if isCt:
            # Remove plots which are already displayed
            names = set([])
            for widget in widgets:
                plotModel = widget.plotModel()
                if plotModel is not None:
                    channels = model_helper.getChannelNamesDisplayedAsValue(plotModel)
                    names.update(channels)

            for p in list(availablePlots):
                channels = set(model_helper.getChannelNamesDisplayedAsValue(p))
                if len(channels - names) == 0:
                    # All the channels are already displayed
                    availablePlots.remove(p)
        else:
            for widget in widgets:
                compatibleModel = self.__getPlotClassFromWidgetClass(type(widget))
                if compatibleModel is None:
                    _logger.error(
                        "No compatible plot model for widget %s", widget.__class__
                    )
                    plotModel = None
                else:
                    plots = [
                        p for p in availablePlots if isinstance(p, compatibleModel)
                    ]
                    if len(plots) > 0:
                        plotModel = plots[0]
                        availablePlots.remove(plotModel)
                    else:
                        plotModel = compatibleModel()

                if not sameScan:
                    if plotModel.styleStrategy() is None:
                        plotModel.setStyleStrategy(DefaultStyleStrategy())
                    workspace.addPlot(plotModel)
                    widget.setPlotModel(plotModel)

        # There is no way in Qt to tabify a widget to a new floating widget
        # Then this code tabify the new widgets on an existing widget
        # FIXME: This behavior is not really convenient
        widgets = workspace.widgets()
        if len(widgets) == 0:
            lastTab = None
        else:
            lastTab = widgets[0]

        # Create widgets for unused plots
        window = flint.liveWindow()
        for plotModel in availablePlots:
            if plotModel.styleStrategy() is None:
                plotModel.setStyleStrategy(DefaultStyleStrategy())
            widget = self.__createWidgetFromPlot(window, plotModel)
            workspace.addPlot(plotModel)
            if widget is None:
                continue

            workspace.addWidget(widget)
            if lastTab is None:
                window.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
                widget.setVisible(True)
            else:
                window.tabifyDockWidget(lastTab, widget)
            lastTab = widget

    def __dockClosed(self):
        dock = self.sender()
        flint = self.__flintModel

        propertyWidget = flint.propertyWidget()
        if propertyWidget.focusWidget() is dock:
            propertyWidget.setFocusWidget(None)

        dock.setPlotModel(None)
        dock.setFlintModel(None)
        workspace = flint.workspace()
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

        flint = self.__flintModel
        workspace = flint.workspace()
        widget: qt.QDockWidget = widgetClass(parent)
        widget.setPlotModel(plotModel)
        self.__initNewDock(widget)

        prefix = str(widgetClass.__name__).replace("PlotWidget", "")
        title = self.__getUnusedTitle(prefix, workspace)
        widget.setWindowTitle(title)
        widget.setObjectName(title.lower() + "-dock")
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
