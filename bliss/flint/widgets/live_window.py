# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import List
from typing import Optional
from typing import Dict
from typing import Any

import enum
import functools
import logging

from silx.gui import qt
from silx.gui import utils
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.widgets.property_widget import MainPropertyWidget
from bliss.flint.widgets.scan_status import ScanStatus
from bliss.flint.widgets.ct_widget import CtWidget
from bliss.flint.widgets.positioners_widget import PositionersWidget
from bliss.flint.widgets.extended_dock_widget import MainWindow
from bliss.flint.widgets.colormap_widget import ColormapWidget


_logger = logging.getLogger(__name__)


class _PredefinedLayouts(enum.Enum):
    ONE_STACK = enum.auto()
    ONE_PER_KIND = enum.auto()
    ONE_FOR_IMAGE_AND_MCA = enum.auto()


class LiveWindowConfiguration:
    """Store a live window configuration for serialization"""

    def __init__(self):
        # Mode
        self.show_count_widget: bool = False
        self.show_positioners_widget: bool = False
        self.show_colormap_dialog: bool = False

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        """Inherite the serialization to make sure the object can growup in the
        future"""
        state: Dict[str, Any] = {}
        state.update(self.__dict__)
        return state

    def __setstate__(self, state):
        """Inherite the serialization to make sure the object can growup in the
        future"""
        for k in self.__dict__.keys():
            if k in state:
                v = state.pop(k)
                self.__dict__[k] = v

    def __str__(self):
        return self.__dict__.__str__()


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
        self.__positionersWidget = None
        self.__colormapWidget = None

        self.__initGui()

    def postInit(self):
        colormapWidget = self.colormapWidget(create=False)
        if colormapWidget is not None:
            # Between creation and display this flag have disappeared
            # FIXME: This could be maybe patched in the extended dock impl
            colormapWidget.setWindowFlag(qt.Qt.WindowStaysOnTopHint, True)
            colormapWidget.show()

    def configuration(self) -> LiveWindowConfiguration:
        """Returns a global configuration of this window

        This configuration is stored in the Redis session.
        """
        config = LiveWindowConfiguration()
        displayed = self.__ctWidget is not None
        config.show_count_widget = displayed
        displayed = self.__positionersWidget is not None
        config.show_positioners_widget = displayed
        displayed = self.__colormapWidget is not None
        config.show_colormap_dialog = displayed
        return config

    def setConfiguration(self, config: LiveWindowConfiguration):
        ctWidgetDisplayed = self.__ctWidget is not None
        if config.show_count_widget != ctWidgetDisplayed:
            self.__toggleCtWidget()
        positionersWidgetDisplayed = self.__positionersWidget is not None
        if config.show_positioners_widget != positionersWidgetDisplayed:
            self.__togglePositionersWidget()
        colormapWidget = self.__colormapWidget is not None
        if config.show_colormap_dialog != colormapWidget:
            self.__toggleColormapWidget()

    def __initGui(self):
        scanStatusWidget = ScanStatus(self)
        scanStatusWidget.setObjectName("scan-status-dock")
        propertyWidget = MainPropertyWidget(self)
        propertyWidget.setObjectName("property-widget")

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

        widget = CtWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(self.__flintModel)
        widget.windowClosed.connect(self.__ctWidgetClosed)
        widget.destroyed.connect(self.__ctWidgetClosed)
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

    def __toggleCtWidget(self):
        ctWidget = self.ctWidget(create=False)
        if ctWidget is None:
            self.ctWidget(create=True)
        else:
            ctWidget.deleteLater()

    def __createPositionersWidget(self):
        flintModel = self.flintModel()

        widget = PositionersWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(self.__flintModel)
        widget.windowClosed.connect(self.__ctWidgetClosed)
        widget.destroyed.connect(self.__ctWidgetClosed)
        widget.setObjectName("positioners-dock")

        workspace = flintModel.workspace()
        curveWidget = [w for w in workspace.widgets() if isinstance(w, CurvePlotWidget)]
        curveWidget = curveWidget[0] if len(curveWidget) > 0 else None

        if curveWidget is None:
            self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
            widget.setVisible(True)
        else:
            self.tabifyDockWidget(curveWidget, widget)

        widget.setWindowTitle("Positioners")
        return widget

    def __positionersWidgetClosed(self):
        self.__positionersWidget = None

    def positionersWidget(self, create=True) -> Optional[PositionersWidget]:
        """Returns the widget used to display positioners."""
        if self.__positionersWidget is None and create:
            widget = self.__createPositionersWidget()
            self.__positionersWidget = widget
        return self.__positionersWidget

    def __togglePositionersWidget(self):
        widget = self.positionersWidget(create=False)
        if widget is None:
            self.positionersWidget(create=True)
        else:
            widget.deleteLater()

    def acquireColormapWidget(self, newOwner):
        """Acquire the colormap widget.

        Returns the colormap widget if it was acquired, else returns None.
        """
        if self.__colormapWidget is None:
            return None
        self.__colormapWidget.setOwner(newOwner)
        return self.__colormapWidget

    def ownedColormapWidget(self, owner):
        """Returns the colormap =widget if it was acquired by this widget.

        Else returns None
        """
        colormapWidget = self.__colormapWidget
        if colormapWidget is None:
            return None
        currentOwner = self.__colormapWidget.owner()
        if currentOwner is owner:
            return colormapWidget
        return None

    def __createColormapWidget(self):
        widget = ColormapWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.windowClosed.connect(self.__colormapWidgetClosed)
        widget.destroyed.connect(self.__colormapWidgetClosed)
        widget.setObjectName("colormap-dock")
        widget.setWindowTitle("Colormap")

        self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
        widget.setFloating(True)
        widget.setVisible(True)
        widget.setWindowFlag(qt.Qt.WindowStaysOnTopHint, True)

        return widget

    def __colormapWidgetClosed(self):
        self.__colormapWidget = None

    def colormapWidget(self, create=True) -> Optional[PositionersWidget]:
        """Returns the widget used to display colormaps."""
        if self.__colormapWidget is None and create:
            widget = self.__createColormapWidget()
            self.__colormapWidget = widget
        return self.__colormapWidget

    def __toggleColormapWidget(self):
        widget = self.colormapWidget(create=False)
        if widget is None:
            self.colormapWidget(create=True)
        else:
            widget.deleteLater()

    def scanStatusWidget(self) -> Optional[ScanStatus]:
        """Returns the widget used to display the scan status."""
        return self.__scanStatusWidget

    def __toggleStatus(self):
        widget = self.scanStatusWidget()
        widget.setVisible(not widget.isVisible())

    def propertyWidget(self) -> Optional[MainPropertyWidget]:
        """Returns the widget used to display properties."""
        return self.__propertyWidget

    def __toggleProperty(self):
        widget = self.propertyWidget()
        widget.setVisible(not widget.isVisible())

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
        curvePlotWidget.widget().setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        workspace.addWidget(curvePlotWidget)
        self.setPredefinedLayout(_PredefinedLayouts.ONE_STACK, workspace)

    def createWindowActions(self, menu: qt.QMenu):
        action = qt.QAction(menu)
        action.setText("Scan progress")
        action.setCheckable(True)
        action.triggered.connect(self.__toggleStatus)
        showScanStateAction = action

        action = qt.QAction(menu)
        action.setText("Properties")
        action.setCheckable(True)
        action.triggered.connect(self.__toggleProperty)
        showPropertyAction = action

        action = qt.QAction(menu)
        action.setText("Count")
        action.setCheckable(True)
        action.triggered.connect(self.__toggleCtWidget)
        showCountAction = action

        action = qt.QAction(menu)
        action.setText("Positioners")
        action.setCheckable(True)
        action.triggered.connect(self.__togglePositionersWidget)
        showPositionersAction = action

        action = qt.QAction(menu)
        action.setText("Colormap")
        action.setCheckable(True)
        action.triggered.connect(self.__toggleColormapWidget)
        showColormapAction = action

        def updateActions():
            scanStatus = self.scanStatusWidget()
            showScanStateAction.setChecked(
                scanStatus is not None and scanStatus.isVisible()
            )
            propertyWidget = self.propertyWidget()
            showPropertyAction.setChecked(
                propertyWidget is not None and propertyWidget.isVisible()
            )
            ctWidget = self.ctWidget(create=False)
            showCountAction.setChecked(ctWidget is not None)
            positionersWidget = self.positionersWidget(create=False)
            colormapWidget = self.colormapWidget(create=False)
            showPositionersAction.setChecked(positionersWidget is not None)
            showColormapAction.setChecked(colormapWidget is not None)

        menu.addAction(showScanStateAction)
        menu.addAction(showPropertyAction)
        menu.addAction(showCountAction)
        menu.addAction(showPositionersAction)
        menu.addAction(showColormapAction)
        menu.aboutToShow.connect(updateActions)

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
                others.append(widget)
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
        ctWidget = self.ctWidget(create=False)
        if ctWidget is not None:
            widgets.append(ctWidget)
        positionersWidget = self.positionersWidget(create=False)
        if positionersWidget is not None:
            widgets.append(positionersWidget)
        colormapWidget = self.colormapWidget(create=False)

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

        if colormapWidget is not None:
            self.addDockWidget(qt.Qt.RightDockWidgetArea, colormapWidget)
            colormapWidget.setFloating(True)
            colormapWidget.setVisible(True)
