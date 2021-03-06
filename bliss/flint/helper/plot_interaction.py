# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Dict
from typing import Sequence
from typing import Optional
from typing import Any

import numpy
import logging
import typing

from silx.gui import qt, icons
from silx.gui.plot.actions import PlotAction
from silx.gui.plot import PlotWidget
from silx.gui.plot import MaskToolsWidget
from silx.gui.colors import rgba
from silx.gui.plot.items.roi import RectangleROI
from silx.gui.plot.items.roi import PointROI
from silx.gui.plot.items.roi import RegionOfInterest
from silx.gui.plot.tools.roi import RegionOfInterestManager

from bliss.controllers.lima import roi as lima_roi
from bliss.flint.widgets.roi_selection_widget import RoiSelectionWidget
from bliss.flint.widgets.utils import rois as extra_rois

_logger = logging.getLogger(__name__)


class DrawModeAction(PlotAction):
    """Action that control drawing mode"""

    _MODES = {  # shape: (icon, text, tooltip
        "rectangle": (
            "shape-rectangle",
            "Rectangle selection",
            "Select a rectangular region",
        ),
        "line": ("shape-diagonal", "Line selection", "Select a line"),
        "hline": ("shape-horizontal", "H. line selection", "Select a horizontal line"),
        "vline": ("shape-vertical", "V. line selection", "Select a vertical line"),
        "polygon": ("shape-polygon", "Polygon selection", "Select a polygon"),
    }

    def __init__(self, plot, parent=None):
        self._shape = "polygon"
        self._label = None
        self._color = "black"
        self._width = None
        icon, text, tooltip = self._MODES[self._shape]

        super(DrawModeAction, self).__init__(
            plot,
            icon=icon,
            text=text,
            tooltip=tooltip,
            triggered=self._actionTriggered,
            checkable=True,
            parent=parent,
        )

        # Listen to mode change
        self.plot.sigInteractiveModeChanged.connect(self._modeChanged)
        # Init the state
        self._modeChanged(None)

    def _update(self):
        if self.isChecked():
            self._actionTriggered()

    def setShape(self, shape):
        self._shape = shape
        icon, text, tooltip = self._MODES[self._shape]
        self.setIcon(icons.getQIcon(icon))
        self.setText(text)
        self.setToolTip(tooltip)
        self._update()

    def getShape(self):
        return self._shape

    def setColor(self, color):
        self._color = rgba(color)
        self._update()

    def getColor(self):
        return qt.QColor.fromRgbF(*self._color)

    def setLabel(self, label):
        self._label = label
        self._update()

    def getLabel(self):
        return self._label

    def setWidth(self, width):
        self._width = width
        self._update()

    def getWidth(self):
        return self._width

    def _modeChanged(self, source):
        modeDict = self.plot.getInteractiveMode()
        old = self.blockSignals(True)
        self.setChecked(
            modeDict["mode"] == "draw"
            and modeDict["shape"] == self._shape
            and modeDict["label"] == self._label
        )
        self.blockSignals(old)

    def _actionTriggered(self, checked=False):
        self.plot.setInteractiveMode(
            "draw",
            source=self,
            shape=self._shape,
            color=self._color,
            label=self._label,
            width=self._width,
        )


class Selector(qt.QObject):
    """Handles the selection of things

    :param parent: QObject's parent
    """

    selectionChanged = qt.Signal()
    """Signal emitted whenever the selection has changed.
    """

    selectionFinished = qt.Signal()
    """Signal emitted when selection is terminated.
    """

    def __init__(self, parent: qt.QObject = None):
        super(Selector, self).__init__(parent=parent)

    def selection(self):
        """Returns the current selection
        """
        return None

    def reset(self):
        """Clear the current selection"""

    def start(self):
        """Start the selection"""

    def stop(self):
        """Stop the selection.

        After that it should not be possible to start it again."""


class ShapeSelector(Selector):
    def __init__(self, parent=None):
        assert isinstance(parent, PlotWidget)
        super(ShapeSelector, self).__init__(parent)
        self._isSelectionRunning = False
        self._selection = ()
        self._itemId = "%s-%s" % (self.__class__.__name__, id(self))
        self._shape: str = ""

    def setShapeSelection(self, shape):
        """
        Set the kind of shape to use durig the selection.

        :param str shape: The shape to select in:
            'rectangle', 'line', 'polygon', 'hline', 'vline'
        """
        self._shape = shape

    # Style

    def color(self):
        """Returns the color used for the selection shape

        :rtype: QColor
        """
        return self._modeAction.getColor()

    def setColor(self, color):
        """Set the color used for the selection shape

        :param color: The color to use for selection shape as
           either a color name, a QColor, a list of uint8 or float in [0, 1].
        """
        self._modeAction.setColor(color)
        self._updateShape()

    # Control selection

    def selection(self):
        """Returns selection control point coordinates

        Returns an empty tuple if there is no selection

        :return: Nx2 (x, y) coordinates or an empty tuple.
        """
        return tuple(zip(*self._selection))

    def _setSelection(self, x, y):
        """Set the selection shape control points.

        Use :meth:`reset` to remove the selection.

        :param x: X coordinates of control points
        :param y: Y coordinates of control points
        """
        selection = x, y
        if selection != self._selection:
            self._selection = selection
            self._updateShape()
            self.selectionChanged.emit()

    def reset(self):
        """Clear the rectangle selection"""
        if self._selection:
            self._selection = ()
            self._updateShape()
            self.selectionChanged.emit()

    def start(self):
        """Start requiring user to select a shape
        """
        plot = self.parent()
        if plot is None:
            raise RuntimeError("No plot to perform selection")

        self.stop()
        self.reset()

        # Add a toolbar to plot
        self._toolbar = qt.QToolBar("Selection")
        self._modeAction = DrawModeAction(plot=plot)
        self._modeAction.setLabel(self._itemId)
        self._modeAction.setColor(rgba("red"))
        toolButton = qt.QToolButton()
        toolButton.setDefaultAction(self._modeAction)
        toolButton.setToolButtonStyle(qt.Qt.ToolButtonTextBesideIcon)
        self._toolbar.addWidget(toolButton)

        assert self._shape in ("rectangle", "line", "polygon", "hline", "vline")

        self._modeAction.setShape(self._shape)
        self._modeAction.trigger()  # To set the interaction mode

        self._isSelectionRunning = True

        plot.sigPlotSignal.connect(self._handleDraw)

        self._toolbar.show()
        plot.addToolBar(qt.Qt.BottomToolBarArea, self._toolbar)

    def stop(self):
        """Stop shape selection"""
        if not self._isSelectionRunning:
            return

        plot = self.parent()
        if plot is None:
            return

        mode = plot.getInteractiveMode()
        if mode["mode"] == "draw" and mode["label"] == self._itemId:
            plot.setInteractiveMode("zoom")  # This disconnects draw handler

        plot.sigPlotSignal.disconnect(self._handleDraw)

        plot.removeToolBar(self._toolbar)

        self._isSelectionRunning = False
        self.selectionFinished.emit()

    def _handleDraw(self, event):
        """Handle shape drawing event"""
        if (
            event["event"] == "drawingFinished"
            and event["parameters"]["label"] == self._itemId
        ):
            self._setSelection(event["xdata"], event["ydata"])
            self.stop()

    def _updateShape(self):
        """Update shape on the plot"""
        plot = self.parent()
        if plot is not None:
            if not self._selection:
                plot.remove(legend=self._itemId, kind="item")

            else:
                x, y = self._selection
                shape = self._modeAction.getShape()
                if shape == "line":
                    shape = "polylines"

                plot.addItem(
                    x,
                    y,
                    legend=self._itemId,
                    shape=shape,
                    color=rgba(self._modeAction.getColor()),
                    fill=False,
                )


class PointsSelector(Selector):
    def __init__(self, parent):
        assert isinstance(parent, PlotWidget)
        super(PointsSelector, self).__init__(parent)

        self._manager = RegionOfInterestManager(parent)
        self._manager.sigRoiAdded.connect(self._roiAdded)
        self._manager.sigInteractiveRoiCreated.connect(self._roiCreated)
        self._totalPoints = 0
        self.__widget = None
        self._selection = None

    def setNbPoints(self, nbPoints):
        """
        Set the number of points requested for the selection.

        :param int nbPoints: Number of points to select
        """
        self._totalPoints = nbPoints

    def selection(self):
        """Returns the selection"""
        if self._manager.isStarted():
            rois = [r for r in self._manager.getRois() if isinstance(r, PointROI)]
            pos = [tuple(r.getPosition()) for r in rois]
            return tuple(pos)
        else:
            return self._selection

    def _roiAdded(self):
        rois = self._manager.getRois()
        self._updateStatusBar()
        if len(rois) >= self._totalPoints:
            self.stop()

    def _roiCreated(self, roi):
        rois = self._manager.getRois()
        roi.setName("%d" % len(rois))
        roi.setColor("pink")

    def eventFilter(self, obj, event):
        """Event filter for plot hide and key event"""
        if event.type() == qt.QEvent.Hide:
            self.stop()

        elif event.type() == qt.QEvent.KeyPress:
            if event.key() in (qt.Qt.Key_Delete, qt.Qt.Key_Backspace) or (
                event.key() == qt.Qt.Key_Z and event.modifiers() & qt.Qt.ControlModifier
            ):
                self._removeLastInput()
                return True  # Stop further handling of those keys

            elif event.key() == qt.Qt.Key_Return:
                self.stop()
                return True  # Stop further handling of those keys

        return super(PointsSelector, self).eventFilter(obj, event)

    def _removeLastInput(self):
        rois = self._manager.getRois()
        if len(rois) == 0:
            return
        roi = rois[-1]
        self._manager.removeRoi(roi)
        self._updateStatusBar()
        self.selectionChanged.emit()

    def start(self):
        """Start interactive selection of points
        """
        self.stop()
        self.reset()

        plot = self.parent()
        if plot is None:
            raise RuntimeError("No plot to perform selection")

        plot.installEventFilter(self)

        self.__widget = qt.QToolButton(plot)
        action = self._manager.getInteractionModeAction(PointROI)
        self.__widget.setDefaultAction(action)
        action.trigger()
        plot.statusBar().addPermanentWidget(self.__widget)

        self._updateStatusBar()

    def stop(self):
        """Stop interactive point selection"""
        if not self._manager.isStarted():
            return

        plot = self.parent()
        if plot is None:
            return

        # Save the current state
        self._selection = self.selection()

        self._manager.clear()
        self._manager.stop()
        plot.removeEventFilter(self)
        statusBar = plot.statusBar()
        statusBar.clearMessage()
        statusBar.removeWidget(self.__widget)
        self.__widget.deleteLater()
        self.__widget = None
        self.selectionFinished.emit()

    def reset(self):
        """Reset selected points"""
        plot = self.parent()
        if plot is None:
            return
        self._manager.clear()
        self._updateStatusBar()
        self.selectionChanged.emit()

    def _updateStatusBar(self):
        """Update status bar message"""
        plot = self.parent()
        if plot is None:
            return

        rois = self._manager.getRois()
        msg = "Select %d/%d input points" % (len(rois), self._totalPoints)
        plot.statusBar().showMessage(msg)


class ShapesSelector(Selector):
    def __init__(self, parent=None):
        assert isinstance(parent, PlotWidget)
        super(ShapesSelector, self).__init__(parent=parent)
        self.__initialShapes: Sequence[Dict] = ()
        self.__timeout = None
        self.__dock = None
        self.__roiWidget = None
        self.__selection = None
        self.__kinds: typing.List[RegionOfInterest] = []
        self.__mapping = {
            "rectangle": RectangleROI,
            "lima-rectangle": extra_rois.LimaRectRoi,
            "lima-arc": extra_rois.LimaArcRoi,
            "lima-vertical-profile": extra_rois.LimaVProfileRoi,
            "lima-horizontal-profile": extra_rois.LimaHProfileRoi,
        }

    def setKinds(self, kinds=typing.List[str]):
        self.__kinds.clear()
        for kind in kinds:
            if kind not in self.__mapping:
                raise RuntimeError("ROI kind '%s' is not supported" % kind)
            roiClass = self.__mapping[kind]
            self.__kinds.append(roiClass)

    def setInitialShapes(
        self, initialShapes: Optional[Sequence[lima_roi._BaseRoi]] = None
    ):
        if initialShapes is None:
            initialShapes = []
        self.__initialShapes = initialShapes

    def setTimeout(self, timeout):
        self.__timeout = timeout

    def __roisToGui(self, shapes: Sequence[Any]) -> Sequence[RegionOfInterest]:
        rois = []
        for shape in shapes:
            if isinstance(shape, dict):
                kind = shape["kind"].lower()
                assert kind == "rectangle"
                x, y = map(int, map(round, shape["origin"]))
                w, h = map(int, map(round, shape["size"]))
                roi = RectangleROI()
                roi.setGeometry(origin=(x, y), size=(w, h))
                roi.setName(shape["label"])
            elif isinstance(shape, lima_roi.RoiProfile):
                if shape.mode == "horizontal":
                    roi = extra_rois.LimaHProfileRoi()
                elif shape.mode == "vertical":
                    roi = extra_rois.LimaVProfileRoi()
                else:
                    _logger.error("RoiProfile mode '%s' unsupported", roi.mode)
                    continue
                roi.setGeometry(
                    origin=(shape.x, shape.y), size=(shape.width, shape.height)
                )
                roi.setName(shape.name)
            elif isinstance(shape, lima_roi.Roi):
                roi = extra_rois.LimaRectRoi()
                roi.setGeometry(
                    origin=(shape.x, shape.y), size=(shape.width, shape.height)
                )
                roi.setName(shape.name)
            elif isinstance(shape, lima_roi.ArcRoi):
                roi = extra_rois.LimaArcRoi()
                roi.setGeometry(
                    center=(shape.cx, shape.cy),
                    innerRadius=shape.r1,
                    outerRadius=shape.r2,
                    startAngle=numpy.deg2rad(shape.a1),
                    endAngle=numpy.deg2rad(shape.a2),
                )
                roi.setName(shape.name)
            else:
                _logger.error("Unknown ROI kind '%s'", type(roi))
                continue
            rois.append(roi)
        return rois

    def __roisFromGui(self, rois: Sequence[RegionOfInterest]) -> Sequence[Dict]:
        shapes = []
        for roi in rois:
            if isinstance(roi, RectangleROI):
                x, y = roi.getOrigin()
                w, h = roi.getSize()
                name = roi.getName()
                if isinstance(roi, extra_rois.LimaHProfileRoi):
                    mode = "horizontal"
                    shape = lima_roi.RoiProfile(x, y, w, h, mode=mode, name=name)
                elif isinstance(roi, extra_rois.LimaVProfileRoi):
                    mode = "vertical"
                    shape = lima_roi.RoiProfile(x, y, w, h, mode=mode, name=name)
                elif isinstance(roi, extra_rois.LimaRectRoi):
                    shape = lima_roi.Roi(x, y, w, h, name=name)
                else:
                    shape = dict(
                        kind="Rectangle", origin=(x, y), size=(w, h), label=name
                    )
            elif isinstance(roi, extra_rois.LimaArcRoi):
                cx = roi.getCenter()[0]
                cy = roi.getCenter()[1]
                r1 = roi.getInnerRadius()
                r2 = roi.getOuterRadius()
                a1 = numpy.rad2deg(roi.getStartAngle())
                a2 = numpy.rad2deg(roi.getEndAngle())
                name = roi.getName()
                shape = lima_roi.ArcRoi(cx, cy, r1, r2, a1, a2, name=name)
            else:
                _logger.error(
                    "Unsupported ROI kind %s. ROI skipped from results", type(roi)
                )
                continue
            shapes.append(shape)
        return shapes

    def start(self):
        plot = self.parent()

        roiWidget = RoiSelectionWidget(plot, kinds=self.__kinds)
        dock = qt.QDockWidget("ROI selection", parent=plot)
        dock.setWidget(roiWidget)
        plot.addTabbedDockWidget(dock)
        rois = self.__roisToGui(self.__initialShapes)
        for roi in rois:
            roiWidget.add_roi(roi)
        roiWidget.selectionFinished.connect(self.__selectionFinished)
        dock.show()

        self.__dock = dock
        self.__roiWidget = roiWidget

        if self.__timeout is not None:
            qt.QTimer.singleShot(self.__timeout * 1000, self.__selectionCancelled)

    def stop(self):
        if self.__dock is None:
            return
        plot = self.parent()
        plot.removeDockWidget(self.__dock)
        if self.__roiWidget is not None:
            self.__roiWidget.selectionFinished.disconnect(self.__selectionFinished)
            self.__roiWidget.clear()
        self.__dock = None
        self.__roiWidget = None

    def selection(self):
        """Returns the selection"""
        return self.__selection

    def __selectionCancelled(self):
        if self.__roiWidget is not None:
            self.stop()
            self.__selection = None
            self.selectionFinished.emit()

    def __selectionFinished(self, selection: Sequence[RegionOfInterest]):
        shapes = self.__roisFromGui(selection)
        self.__selection = shapes
        self.stop()
        self.selectionFinished.emit()


class MaskToolsDockWidget(MaskToolsWidget.MaskToolsDockWidget):
    """Mask tool which make sure the current mask is always used anyway the
    activate item change"""

    def __init__(self, parent=None, plot=None, name="Mask"):
        self._restoreBehavior = self._RestoreMaskBehaviour(self, plot)
        MaskToolsWidget.MaskToolsDockWidget.__init__(
            self, parent=parent, plot=plot, name=name
        )

    class _RestoreMaskBehaviour:
        def __init__(self, parent, plot):
            self.__mask = None
            self.parent = parent
            plot.sigActiveImageChanged.connect(self.activeItemChanged)

        def activeItemChanged(self, previous, legend):
            if previous is not None:
                self.__mask = self.parent.getSelectionMask(copy=True)
            if legend is not None:
                self.parent.setSelectionMask(self.__mask, copy=False)


class MaskImageSelector(Selector):
    def __init__(self, parent=None):
        assert isinstance(parent, PlotWidget)
        super(MaskImageSelector, self).__init__(parent=parent)
        self.__timeout = None
        self.__selection = None
        self.__dock: MaskToolsDockWidget = None
        self.__initialMask: Optional[numpy.ndarray] = None
        self.__directory: Optional[str] = None

    def setInitialMask(self, mask: numpy.ndarray, copy=True):
        if copy and mask is not None:
            mask = numpy.array(mask)
        self.__initialMask = mask

    def setDirectory(self, directory: str):
        self.__directory = directory

    def setTimeout(self, timeout):
        self.__timeout = timeout

    def start(self):
        plot = self.parent()

        dock = MaskToolsDockWidget(plot=plot, name="Mask tools")
        maskTool = dock.widget()
        if self.__directory is not None:
            maskTool.setMaskFileDirectory(self.__directory)

        # Inject a button to validate the selection
        group = maskTool.otherToolGroup
        layout = group.layout()
        self._validate = qt.QPushButton("Validate")
        size = self._validate.sizeHint()
        self._validate.setMinimumHeight(int(size.height() * 1.5))
        self._validate.clicked.connect(self.__selectionFinished)
        layout.addWidget(self._validate)

        plot.addTabbedDockWidget(dock)

        try:
            plot.setUpdatesEnabled(False)
            dock.setUpdatesEnabled(False)

            dock.show()

            # Must be done after the show else it is not working
            dock.setSelectionMask(self.__initialMask, copy=False)
            # Inject a default selection by default
            maskTool.rectAction.trigger()

            dock.visibilityChanged.connect(self.__selectionCancelled)
        finally:
            plot.setUpdatesEnabled(True)
            dock.setUpdatesEnabled(True)

        self.__dock = dock

        if self.__timeout is not None:
            qt.QTimer.singleShot(self.__timeout * 1000, self.__selectionCancelled)

    def stop(self):
        dock = self.__dock
        if dock is None:
            return
        self.__dock.resetSelectionMask()
        self.__dock = None
        dock.visibilityChanged.disconnect(self.__selectionCancelled)
        plot = self.parent()
        plot.removeDockWidget(dock)

    def selection(self):
        """Returns the selection"""
        return self.__selection

    def __selectionCancelled(self):
        if self.__dock is not None:
            self.stop()
            self.__selection = None
            self.selectionFinished.emit()

    def __selectionFinished(self):
        mask = self.__dock.getSelectionMask(copy=True)
        self.stop()
        self.__selection = mask
        self.selectionFinished.emit()
