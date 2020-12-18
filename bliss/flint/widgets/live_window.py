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
import weakref

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
        self.colormap_geometry: Optional[qt.QRect] = None

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
        self.__lastColormapWidgetFloatingGeometry = None

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
        # FIXME Must be part of the ColormapDialog config
        config.colormap_geometry = self.__lastColormapWidgetFloatingGeometry
        return config

    def setConfiguration(self, config: LiveWindowConfiguration):
        # FIXME: backward compatibility with BLISS 1.6
        # FIXME: this flag should be removed to only use widgets from workspace
        ctWidgetDisplayed = self.ctWidget(create=False) is not None
        if config.show_count_widget and not ctWidgetDisplayed:
            self.__toggleCtWidget()
        positionersWidgetDisplayed = self.positionersWidget(create=False) is not None
        if config.show_positioners_widget and not positionersWidgetDisplayed:
            self.__togglePositionersWidget()
        colormapWidget = self.colormapWidget(create=False) is not None
        if config.show_colormap_dialog and not colormapWidget:
            self.__toggleColormapWidget()
        self.__lastColormapWidgetFloatingGeometry = config.colormap_geometry

    def updateFromWorkspace(self, workspace: flint_model.Workspace):
        """Synchronize the available widgets from the current workspace"""
        widgets = workspace.widgets()

        def get_weak_widget(classObj):
            selectedWidgets = [w for w in widgets if isinstance(w, classObj)]
            if len(selectedWidgets) > 0:
                return weakref.ref(selectedWidgets[0])
            else:
                return None

        self.__ctWidget = get_weak_widget(CtWidget)
        self.__positionersWidget = get_weak_widget(PositionersWidget)
        self.__colormapWidget = get_weak_widget(ColormapWidget)
        if self.__colormapWidget is not None:
            widget = self.__colormapWidget()
            widget.windowClosed.connect(self.__colormapWidgetClosed)
        self.__scanStatusWidget = get_weak_widget(ScanStatus)
        self.__propertyWidget = get_weak_widget(MainPropertyWidget)

    def __createScanStatus(self):
        widget = ScanStatus(self)
        widget.setObjectName("scan-status-dock")
        widget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred
        )

        manager = self.__flintModel.mainManager()
        if manager is not None:
            manager.registerDock(widget)
        return widget

    def __createPropertyWidget(self):
        widget = MainPropertyWidget(self)
        widget.setObjectName("property-widget")
        widget.widget().setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding
        )

        manager = self.__flintModel.mainManager()
        if manager is not None:
            manager.registerDock(widget)
        return widget

    def __createCtWidget(self):
        flintModel = self.flintModel()
        widget = CtWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(self.__flintModel)
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

        manager = self.__flintModel.mainManager()
        if manager is not None:
            manager.registerDock(widget)
        return widget

    def __createPositionersWidget(self):
        flintModel = self.flintModel()

        widget = PositionersWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(self.__flintModel)
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

        manager = self.__flintModel.mainManager()
        if manager is not None:
            manager.registerDock(widget)
        return widget

    def __createColormapWidget(self):
        widget = ColormapWidget(self)
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)

        widget.windowClosed.connect(self.__colormapWidgetClosed)
        widget.setObjectName("colormap-dock")
        widget.setWindowTitle("Colormap")

        self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
        widget.setFloating(True)
        if self.__lastColormapWidgetFloatingGeometry is not None:
            widget.setGeometry(self.__lastColormapWidgetFloatingGeometry)
        widget.setVisible(True)
        widget.setWindowFlag(qt.Qt.WindowStaysOnTopHint, True)

        manager = self.__flintModel.mainManager()
        if manager is not None:
            manager.registerDock(widget)
        return widget

    def __colormapWidgetClosed(self):
        colormapWidget = self.sender()
        if colormapWidget is not None:
            colormapWidget.windowClosed.disconnect(self.__colormapWidgetClosed)
            if colormapWidget.isFloating():
                self.__lastColormapWidgetFloatingGeometry = colormapWidget.geometry()

    def ctWidget(self, create=True) -> Optional[CtWidget]:
        """Returns the widget used to display ct."""
        if self.__ctWidget is None:
            widget = None
        else:
            widget = self.__ctWidget()
        if widget is None and create:
            widget = self.__createCtWidget()
            self.__ctWidget = weakref.ref(widget)
        return widget

    def positionersWidget(self, create=True) -> Optional[PositionersWidget]:
        """Returns the widget used to display positioners."""
        if self.__positionersWidget is None:
            widget = None
        else:
            widget = self.__positionersWidget()
        if widget is None and create:
            widget = self.__createPositionersWidget()
            self.__positionersWidget = weakref.ref(widget)
        return widget

    def acquireColormapWidget(self, newOwner):
        """Acquire the colormap widget.

        Returns the colormap widget if it was acquired, else returns None.
        """
        colormapWidget = self.colormapWidget(create=False)
        if colormapWidget is None:
            return None
        colormapWidget.setOwner(newOwner)
        return colormapWidget

    def ownedColormapWidget(self, owner):
        """Returns the colormap widget if it was acquired by this widget.

        Else returns None
        """
        colormapWidget = self.colormapWidget(create=False)
        if colormapWidget is None:
            return None
        currentOwner = colormapWidget.owner()
        if currentOwner is owner:
            return colormapWidget
        return None

    def colormapWidget(self, create=True, show=False) -> Optional[PositionersWidget]:
        """Returns the widget used to display colormaps."""
        if self.__colormapWidget is None:
            widget = None
        else:
            widget = self.__colormapWidget()
        if widget is None and create:
            widget = self.__createColormapWidget()
            self.__colormapWidget = weakref.ref(widget)
        if show and widget is not None:
            widget.show()
            widget.raise_()
        return widget

    def scanStatusWidget(self, create=True) -> Optional[ScanStatus]:
        """Returns the widget used to display the scan status."""
        if self.__scanStatusWidget is None:
            widget = None
        else:
            widget = self.__scanStatusWidget()
        if widget is None and create:
            widget = self.__createScanStatus()
            self.__scanStatusWidget = weakref.ref(widget)
        return widget

    def propertyWidget(self, create=True) -> Optional[MainPropertyWidget]:
        """Returns the widget used to display properties."""
        if self.__propertyWidget is None:
            widget = None
        else:
            widget = self.__propertyWidget()
        if widget is None and create:
            widget = self.__createPropertyWidget()
            self.__propertyWidget = weakref.ref(widget)
        return widget

    def __toggleGeneric(self, getter, visibility):
        """Toggle a widget using the common pattern of this live widget

        This is a little cryptic but it avoid duplication.

        Argument:
            getter: A callable which returns the widget if it exists. Else,
                depending on `create=False`, it returns None, or create and
                return the new widget
            visibility: If true, use `setVisible` to toggle the widget, else
                create and destroy it
        """
        widget = getter(create=False)
        if widget is None:
            getter()
        else:
            if visibility:
                widget.setVisible(not widget.isVisible())
            else:
                if hasattr(widget, "windowClosed"):
                    # FIXME: It would be better to move it at another place
                    widget.windowClosed.emit()
                widget.deleteLater()

    def __toggleStatus(self):
        self.__toggleGeneric(self.scanStatusWidget, visibility=True)

    def __toggleProperty(self):
        self.__toggleGeneric(self.propertyWidget, visibility=True)

    def __toggleCtWidget(self):
        self.__toggleGeneric(self.ctWidget, visibility=False)

    def __togglePositionersWidget(self):
        self.__toggleGeneric(self.positionersWidget, visibility=False)

    def __toggleColormapWidget(self):
        self.__toggleGeneric(self.colormapWidget, visibility=False)

    def setFlintModel(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel
        widget = self.scanStatusWidget(create=False)
        if widget is not None:
            widget.setFlintModel(flintModel)
        widget = self.ctWidget(create=False)
        if widget is not None:
            widget.setFlintModel(flintModel)

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
            scanStatus = self.scanStatusWidget(create=False)
            showScanStateAction.setChecked(
                scanStatus is not None and scanStatus.isVisible()
            )
            propertyWidget = self.propertyWidget(create=False)
            showPropertyAction.setChecked(
                propertyWidget is not None and propertyWidget.isVisible()
            )
            ctWidget = self.ctWidget(create=False)
            showCountAction.setChecked(ctWidget is not None)
            positionersWidget = self.positionersWidget(create=False)
            showPositionersAction.setChecked(positionersWidget is not None)
            colormapWidget = self.colormapWidget(create=False)
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
        # FIXME: This function have to be reworked
        # The layout constructed with a dedicated module

        flintModel = self.flintModel()
        if workspace is None:
            workspace = flintModel.workspace()

        statusWidget = self.scanStatusWidget()
        propertyWidget = self.propertyWidget()

        widgets = workspace.widgets()
        # FIXME Remove me: this widget already have to be part of the widgets
        ctWidget = self.ctWidget(create=False)
        if ctWidget is not None:
            if ctWidget not in widgets:
                widgets.append(ctWidget)
        # FIXME Remove me: this widget already have to be part of the widgets
        positionersWidget = self.positionersWidget(create=False)
        if positionersWidget is not None:
            if positionersWidget not in widgets:
                widgets.append(positionersWidget)

        allWidgets = list(widgets)
        if statusWidget in widgets:
            widgets.remove(statusWidget)
        if propertyWidget in widgets:
            widgets.remove(propertyWidget)

        colormapWidget = self.colormapWidget(create=False)

        with utils.blockSignals(self):
            if layoutKind == _PredefinedLayouts.ONE_STACK:
                self.__freeDockSpace(allWidgets)

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
                self.__freeDockSpace(allWidgets)

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
                self.__freeDockSpace(allWidgets)

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
            if self.__lastColormapWidgetFloatingGeometry is not None:
                colormapWidget.setGeometry(self.__lastColormapWidgetFloatingGeometry)
