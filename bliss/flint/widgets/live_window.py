# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import List
from typing import Optional

import enum
import functools

from silx.gui import qt
from silx.gui import utils
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.widgets.property_widget import MainPropertyWidget
from bliss.flint.widgets.scan_status import ScanStatus
from bliss.flint.widgets.ct_widget import CtWidget
from bliss.flint.widgets.extended_dock_widget import MainWindow


class _PredefinedLayouts(enum.Enum):
    ONE_STACK = enum.auto()
    ONE_PER_KIND = enum.auto()
    ONE_FOR_IMAGE_AND_MCA = enum.auto()


class LiveWindow(MainWindow):
    """Manage the GUI relative to live scans."""

    def __init__(self, parent=None):
        MainWindow.__init__(self, parent=parent)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            self.dockOptions()
            | qt.QMainWindow.AllowNestedDocks
            | qt.QMainWindow.AllowTabbedDocks
            | qt.QMainWindow.GroupedDragging
            | qt.QMainWindow.AnimatedDocks
            # | qt.QMainWindow.VerticalTabs
        )
        self.__flintModel: flint_model.FlintState = None

        self.tabifiedDockWidgetActivated.connect(self.__tabActivated)
        self.setLayoutLocked(True)

        self.__scanStatusWidget = None
        self.__propertyWidget = None
        self.__ctWidget = None

        self.__initGui()

    def __initGui(self):
        scanStatusWidget = ScanStatus(self)
        scanStatusWidget.setObjectName("scan-status-dock")
        scanStatusWidget.setFeatures(
            scanStatusWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )

        propertyWidget = MainPropertyWidget(self)
        propertyWidget.setObjectName("property-widget")
        propertyWidget.setFeatures(
            propertyWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )

        scanStatusWidget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred
        )
        propertyWidget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding
        )
        self.__scanStatusWidget = scanStatusWidget
        self.__propertyWidget = propertyWidget

    def __createCtWidget(self):
        flintModel = self.flintModel()
        from bliss.flint.widgets import ct_widget

        widget = ct_widget.CtWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(self.__flintModel)
        widget.windowClosed.connect(self.__ctWidgetClosed)
        widget.setObjectName("ct-dock")

        workspace = flintModel.workspace()
        curveWidget = [w for w in workspace.widgets() if isinstance(w, CurvePlotWidget)]
        curveWidget = curveWidget[0] if len(curveWidget) > 0 else None

        if curveWidget is None:
            self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
            widget.setVisible(True)
        else:
            self.tabifyDockWidget(curveWidget, widget)

        widget.setWindowTitle("Count")
        return widget

    def __ctWidgetClosed(self):
        self.__ctWidget = None

    def ctWidget(self, create=True) -> Optional[CtWidget]:
        """Returns the widget used to display ct."""
        if self.__ctWidget is None and create:
            widget = self.__createCtWidget()
            self.__ctWidget = widget
        return self.__ctWidget

    def scanStatusWidget(self) -> Optional[ScanStatus]:
        """Returns the widget used to display the scan status."""
        return self.__scanStatusWidget

    def propertyWidget(self) -> Optional[MainPropertyWidget]:
        """Returns the widget used to display properties."""
        return self.__propertyWidget

    def setFlintModel(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        if self.__scanStatusWidget is not None:
            self.__scanStatusWidget.setFlintModel(flintModel)
        if self.__ctWidget is not None:
            self.__ctWidget.setFlintModel(flintModel)

    def flintModel(self) -> flint_model.FlintState:
        assert self.__flintModel is not None
        return self.__flintModel

    def __tabActivated(self, dock: qt.QDockWidget):
        if hasattr(dock, "widgetActivated"):
            dock.widgetActivated.emit(dock)

    def feedDefaultWorkspace(self, flintModel, workspace):
        curvePlotWidget = CurvePlotWidget(parent=self)
        curvePlotWidget.setFlintModel(flintModel)
        curvePlotWidget.setObjectName("curve1-dock")
        curvePlotWidget.setWindowTitle("Curve1")
        curvePlotWidget.setFeatures(
            curvePlotWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )
        curvePlotWidget.widget().setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        workspace.addWidget(curvePlotWidget)
        self.setPredefinedLayout(_PredefinedLayouts.ONE_STACK, workspace)

    def createLayoutActions(self, parent: qt.QObject) -> List[qt.QAction]:
        result = []

        action = qt.QAction(parent)
        action.setText("Layout with a single stack")
        action.triggered.connect(
            functools.partial(
                self.__clickPredefinedLayout, _PredefinedLayouts.ONE_STACK
            )
        )
        icon = icons.getQIcon("flint:icons/layout-one-stack")
        action.setIcon(icon)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("Curve/scatter on bottom, image/MCA on stacks")
        action.triggered.connect(
            functools.partial(
                self.__clickPredefinedLayout, _PredefinedLayouts.ONE_FOR_IMAGE_AND_MCA
            )
        )
        icon = icons.getQIcon("flint:icons/layout-one-for-image-and-mca")
        action.setIcon(icon)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("A stack per plot kind")
        action.triggered.connect(
            functools.partial(
                self.__clickPredefinedLayout, _PredefinedLayouts.ONE_PER_KIND
            )
        )
        icon = icons.getQIcon("flint:icons/layout-one-per-kind")
        action.setIcon(icon)
        result.append(action)

        action = qt.QAction(self)
        action.setText("Lock/unlock the view")
        action.setCheckable(True)
        action.setChecked(self.isLayoutLocked())
        action.toggled[bool].connect(self.setLayoutLocked)
        action.setShortcut("Ctrl+L")
        result.append(action)

        return result

    def __freeDockSpace(self, widgets):
        for widget in widgets:
            widget.setParent(None)
            self.removeDockWidget(widget)

    def __filterWidgetsByTypes(self, widgets):
        curves, scatters, images, mcas, others = [], [], [], [], []
        for widget in widgets:
            name = str(type(widget)).lower()
            if "curve" in name:
                curves.append(widget)
            elif "scatter" in name:
                scatters.append(widget)
            elif "image" in name:
                images.append(widget)
            elif "mca" in name:
                mcas.append(widget)
            else:
                others.append(others)
        return curves, scatters, images, mcas, others

    def customResizeDocks(self, docks, sizes, orientation):
        if ... not in sizes:
            return self.resizeDocks(docks, sizes, orientation)

        size = self.size()
        if orientation == qt.Qt.Vertical:
            size = size.height()
        else:
            size = size.width()

        nb = sizes.count(...)
        remaining = size - sum([s for s in sizes if s is not ...])
        remaining = remaining // nb
        sizes = [s if s is not ... else remaining for s in sizes]
        self.resizeDocks(docks, sizes, orientation)

    def __dockContent(
        self,
        leftSide: qt.QWidget,
        bottomLeft: List[qt.QWidget],
        bottomRight: List[qt.QWidget],
        upLeft: List[qt.QWidget],
        upRight: List[qt.QWidget],
    ):
        holderBottomLeft = qt.QDockWidget(self)
        holderBottomRight = qt.QDockWidget(self)
        holderUpLeft = qt.QDockWidget(self)
        holderUpRight = qt.QDockWidget(self)
        holderUpLeft.setVisible(False)
        holderUpRight.setVisible(False)
        holderBottomLeft.setVisible(False)
        holderBottomRight.setVisible(False)

        self.addDockWidget(qt.Qt.RightDockWidgetArea, holderUpLeft)
        self.customResizeDocks([leftSide, holderUpLeft], [300, ...], qt.Qt.Horizontal)
        self.splitDockWidget(holderUpLeft, holderBottomLeft, qt.Qt.Vertical)
        self.splitDockWidget(holderUpLeft, holderUpRight, qt.Qt.Horizontal)
        self.splitDockWidget(holderBottomLeft, holderBottomRight, qt.Qt.Horizontal)

        def tabOver(first: qt.QWidget, widgets):
            if len(widgets) == 0:
                return
            lastTab = first
            for widget in widgets:
                widget.setParent(self)
                self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
                self.tabifyDockWidget(lastTab, widget)
                widget.setVisible(True)
                lastTab = widget

        tabOver(holderBottomLeft, bottomLeft)
        tabOver(holderBottomRight, bottomRight)
        tabOver(holderUpLeft, upLeft)
        tabOver(holderUpRight, upRight)

        self.removeDockWidget(holderBottomLeft)
        self.removeDockWidget(holderBottomRight)
        self.removeDockWidget(holderUpLeft)
        self.removeDockWidget(holderUpRight)

        holderUpLeft.deleteLater()
        holderUpRight.deleteLater()
        holderBottomLeft.deleteLater()
        holderBottomRight.deleteLater()

    def __clickPredefinedLayout(self, layoutKind: _PredefinedLayouts):
        self.setPredefinedLayout(layoutKind)

    def setPredefinedLayout(
        self, layoutKind: _PredefinedLayouts, workspace: flint_model.Workspace = None
    ):
        statusWidget = self.__scanStatusWidget
        propertyWidget = self.__propertyWidget
        flintModel = self.flintModel()
        if workspace is None:
            workspace = flintModel.workspace()
        widgets = workspace.widgets()

        with utils.blockSignals(self):
            if layoutKind == _PredefinedLayouts.ONE_STACK:
                self.__freeDockSpace(widgets + [statusWidget, propertyWidget])

                statusWidget.setParent(self)
                self.addDockWidget(qt.Qt.LeftDockWidgetArea, statusWidget)
                statusWidget.setVisible(True)

                if len(widgets) > 0:
                    widget = widgets.pop(0)
                    widget.setParent(self)
                    self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
                    self.customResizeDocks(
                        [statusWidget, widget], [300, ...], qt.Qt.Horizontal
                    )
                    widget.setVisible(True)
                    lastTab = widget
                    for widget in widgets:
                        widget.setParent(self)
                        self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
                        self.tabifyDockWidget(lastTab, widget)
                        widget.setVisible(True)
                        lastTab = widget

                propertyWidget.setParent(self)
                self.splitDockWidget(statusWidget, propertyWidget, qt.Qt.Vertical)
                propertyWidget.setVisible(True)
                self.customResizeDocks(
                    [statusWidget, propertyWidget], [100, ...], qt.Qt.Vertical
                )

            elif layoutKind == _PredefinedLayouts.ONE_FOR_IMAGE_AND_MCA:
                self.__freeDockSpace(widgets + [statusWidget, propertyWidget])

                statusWidget.setParent(self)
                self.addDockWidget(qt.Qt.LeftDockWidgetArea, statusWidget)
                statusWidget.setVisible(True)

                curves, scatters, images, mcas, others = self.__filterWidgetsByTypes(
                    widgets
                )
                bottom = curves + scatters + others
                self.__dockContent(
                    leftSide=statusWidget,
                    bottomLeft=bottom,
                    bottomRight=[],
                    upLeft=mcas,
                    upRight=images,
                )

                propertyWidget.setParent(self)
                self.splitDockWidget(statusWidget, propertyWidget, qt.Qt.Vertical)
                propertyWidget.setVisible(True)
                self.customResizeDocks(
                    [statusWidget, propertyWidget], [100, ...], qt.Qt.Vertical
                )

            elif layoutKind == _PredefinedLayouts.ONE_PER_KIND:
                self.__freeDockSpace(widgets + [statusWidget, propertyWidget])

                statusWidget.setParent(self)
                self.addDockWidget(qt.Qt.LeftDockWidgetArea, statusWidget)
                statusWidget.setVisible(True)

                curves, scatters, images, mcas, others = self.__filterWidgetsByTypes(
                    widgets
                )
                bottom = curves + scatters + others
                self.__dockContent(
                    leftSide=statusWidget,
                    bottomLeft=curves + others,
                    bottomRight=scatters,
                    upLeft=mcas,
                    upRight=images,
                )

                propertyWidget.setParent(self)
                self.splitDockWidget(statusWidget, propertyWidget, qt.Qt.Vertical)
                propertyWidget.setVisible(True)
                self.customResizeDocks(
                    [statusWidget, propertyWidget], [100, ...], qt.Qt.Vertical
                )

            else:
                assert False
