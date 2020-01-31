# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import List

import enum
import functools

from silx.gui import qt
from silx.gui import utils
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.widgets.property_widget import MainPropertyWidget
from bliss.flint.widgets.scan_status import ScanStatus


class _PredefinedLayouts(enum.Enum):
    ONE_STACK = enum.auto()
    ONE_PER_KIND = enum.auto()
    ONE_FOR_IMAGE_AND_MCA = enum.auto()


class LiveWindow(qt.QMainWindow):
    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self, parent=parent)
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
        self.__initGui()

    def __initGui(self):
        scanStatusWidget = ScanStatus(self)
        scanStatusWidget.setObjectName("scan-status-dock")
        scanStatusWidget.setFeatures(
            scanStatusWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )

        propertyWidget = MainPropertyWidget(self)
        propertyWidget.setObjectName("property-dock")
        propertyWidget.setFeatures(
            propertyWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )

        scanStatusWidget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred
        )
        propertyWidget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding
        )
        self._tmpStorage = (scanStatusWidget, propertyWidget)

    def setFlintModel(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        scanStatusWidget, propertyWidget = self._tmpStorage
        scanStatusWidget.setFlintModel(flintModel)
        flintModel.setLiveStatusWidget(scanStatusWidget)
        flintModel.setPropertyWidget(propertyWidget)

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
        self.setPredefinedLayout(_PredefinedLayouts.ONE_STACK)

    def createLayoutActions(self, parent: qt.QObject) -> List[qt.QAction]:
        result = []

        action = qt.QAction(parent)
        action.setText("Layout with a single stack")
        action.triggered.connect(
            functools.partial(self.setPredefinedLayout, _PredefinedLayouts.ONE_STACK)
        )
        icon = icons.getQIcon("flint:icons/layout-one-stack")
        action.setIcon(icon)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("Curve/scatter on bottom, image/MCA on stacks")
        action.triggered.connect(
            functools.partial(
                self.setPredefinedLayout, _PredefinedLayouts.ONE_FOR_IMAGE_AND_MCA
            )
        )
        icon = icons.getQIcon("flint:icons/layout-one-for-image-and-mca")
        action.setIcon(icon)
        result.append(action)

        action = qt.QAction(parent)
        action.setText("A stack per plot kind")
        action.triggered.connect(
            functools.partial(self.setPredefinedLayout, _PredefinedLayouts.ONE_PER_KIND)
        )
        icon = icons.getQIcon("flint:icons/layout-one-per-kind")
        action.setIcon(icon)
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

    def setPredefinedLayout(self, layoutKind: _PredefinedLayouts):
        flintModel = self.flintModel()
        statusWidget = flintModel.liveStatusWidget()
        propertyWidget = flintModel.propertyWidget()
        widgets = flintModel.workspace().widgets()

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
