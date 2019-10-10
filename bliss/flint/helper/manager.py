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

import pickle
import logging
from silx.gui import qt

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.helper.style_helper import DefaultStyleStrategy

_logger = logging.getLogger(__name__)


class ManageMainBehaviours(qt.QObject):
    def __init__(self, parent=None):
        super(ManageMainBehaviours, self).__init__(parent=parent)
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__activeDock = None

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
            if hasattr(widget, "createPropertyWidget"):
                window = self.__flintModel.window()
                specificPropertyWidget = widget.createPropertyWidget(window)
                propertyWidget.setWidget(specificPropertyWidget)
            else:
                print("Widget %s do not have propertyWidget factory")
                propertyWidget.setWidget(None)

    def __currentScanChanged(self, previousScan, newScan):
        self.__storeScanIfNeeded(newScan)

    def __storeScanIfNeeded(self, scan: scan_model.Scan):
        if self.__flintModel is None:
            return None
        workspace = self.__flintModel.workspace()
        if workspace is None:
            return None
        for plot in workspace.plots():
            if isinstance(plot, plot_curve_model.CurvePlot):
                if plot.isScansStored():
                    item = plot_curve_model.ScanItem(plot, scan)
                    plot.addItem(item)

    def saveWorkspace(self):
        workspace = self.__flintModel.workspace()
        plots = {}
        for plot in workspace.plots():
            plots[id(plot)] = plot

        widgetDescriptions = []
        for widget in workspace.widgets():
            model = widget.plotModel()
            if model is not None:
                modelId = id(model)
            else:
                modelId = None
            widgetDescriptions.append((widget.objectName(), widget.__class__, modelId))

        window = self.__flintModel.window()
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

        window = self.__flintModel.window()
        for name, widgetClass, modelId in widgetDescriptions:
            widget = widgetClass(window)
            widget.setFlintModel(self.__flintModel)
            widget.setObjectName(name)
            if modelId is not None:
                plot = plots[modelId]
                widget.setPlotModel(plot)
            workspace.addWidget(widget)

        window.restoreState(layout)

        self.__flintModel.setWorkspace(workspace)

    def moveWidgetToWorkspace(self, workspace):
        widgets = self.__flintModel.workspace().popWidgets()

        from bliss.flint.widgets.curve_plot import CurvePlotWidget
        from bliss.flint.widgets.mca_plot import McaPlotWidget
        from bliss.flint.widgets.image_plot import ImagePlotWidget
        from bliss.flint.widgets.scatter_plot import ScatterPlotWidget

        mapping = {}
        mapping[CurvePlotWidget] = plot_curve_model.CurvePlot
        mapping[McaPlotWidget] = plot_item_model.McaPlot
        mapping[ImagePlotWidget] = plot_item_model.ImagePlot
        mapping[ScatterPlotWidget] = plot_item_model.ScatterPlot

        availablePlots = list(workspace.plots())

        for widget in widgets:
            widget.setFlintModel(self.__flintModel)

            compatibleModel = mapping.get(widget.__class__, None)
            if compatibleModel is None:
                print("No compatible class model")
                plotModel = None
            else:
                plots = [p for p in availablePlots if isinstance(p, compatibleModel)]
                if len(plots) > 0:
                    plotModel = plots[0]
                    availablePlots.remove(plotModel)
                else:
                    print("No compatible model")
                    plotModel = compatibleModel()
                    plotModel.setStyleStrategy(DefaultStyleStrategy())
                    workspace.addPlot(plotModel)

            widget.setPlotModel(plotModel)
            workspace.addWidget(widget)

    def updateScanAndPlots(self, scan: scan_model.Scan, plots: List[plot_model.Plot]):
        flint = self.__flintModel
        workspace = flint.workspace()

        # Remove previous plot models
        for widget in workspace.widgets():
            widget.setPlotModel(None)
        for plot in workspace.plots():
            workspace.removePlot(plot)

        # Set the new scan
        flint.setCurrentScan(scan)

        # Reuse/create and connect the widgets

        from bliss.flint.widgets.curve_plot import CurvePlotWidget
        from bliss.flint.widgets.mca_plot import McaPlotWidget
        from bliss.flint.widgets.image_plot import ImagePlotWidget
        from bliss.flint.widgets.scatter_plot import ScatterPlotWidget

        mapping = {}
        mapping[CurvePlotWidget] = plot_curve_model.CurvePlot
        mapping[McaPlotWidget] = plot_item_model.McaPlot
        mapping[ImagePlotWidget] = plot_item_model.ImagePlot
        mapping[ScatterPlotWidget] = plot_item_model.ScatterPlot

        availablePlots = list(plots)
        widgets = self.__flintModel.workspace().widgets()
        for widget in widgets:
            compatibleModel = mapping.get(widget.__class__, None)
            if compatibleModel is None:
                _logger.error(
                    "No compatible plot model for widget %s", widget.__class__
                )
                plotModel = None
            else:
                plots = [p for p in availablePlots if isinstance(p, compatibleModel)]
                if len(plots) > 0:
                    plotModel = plots[0]
                    availablePlots.remove(plotModel)
                else:
                    plotModel = compatibleModel()

            if plotModel.styleStrategy() is None:
                plotModel.setStyleStrategy(DefaultStyleStrategy())
            workspace.addPlot(plotModel)
            widget.setPlotModel(plotModel)

        # FIXME: No way to tab widgets to a new floating widget
        widgets = workspace.widgets()
        if len(widgets) == 0:
            lastTab = None
        else:
            lastTab = widgets[0]

        # Create widgets for unused plots
        for plotModel in availablePlots:
            compatibleWidgetClasses = [
                c for c in mapping if mapping[c] == type(plotModel)
            ]
            if len(compatibleWidgetClasses) == 0:
                _logger.error(
                    "No compatible widget for plot model %s. Plot not displayed.",
                    type(plotModel),
                )
                workspace.addPlot(plotModel)
            else:
                if plotModel.styleStrategy() is None:
                    plotModel.setStyleStrategy(DefaultStyleStrategy())
                compatibleWidgetClass = compatibleWidgetClasses[0]
                window = flint.window()
                widget: qt.QDockWidget = compatibleWidgetClass(window)
                widget.setFlintModel(flint)
                prefix = str(compatibleWidgetClass.__name__).replace("PlotWidget", "")
                title = self.__getUnusedTitle(prefix, workspace)
                widget.setWindowTitle(title)
                widget.setPlotModel(plotModel)
                workspace.addPlot(plotModel)
                workspace.addWidget(widget)
                if lastTab is None:
                    widget.setFloating(True)
                    widget.setVisible(True)
                    widget.updateGeometry()
                else:
                    window.tabifyDockWidget(lastTab, widget)
                lastTab = widget

    def __getUnusedTitle(self, prefix, workspace) -> str:
        for num in range(1, 100):
            title = prefix + str(num)
            for widget in workspace.widgets():
                if widget.windowTitle() == title:
                    break
            else:
                return title
        return title
