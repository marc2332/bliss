# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import numpy
import weakref
import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui import colors
from silx.gui.plot.tools import roi
from silx.gui.plot.items import roi as roi_items
from silx.gui.plot import items
from silx.gui.plot import PlotWidget
from silx.utils.weakref import WeakMethodProxy


_logger = logging.getLogger(__name__)


def _getAutoPrecision(plot):
    def getPrecision(axis):
        vmin, vmax = axis.getLimits()
        delta = numpy.abs(vmax - vmin)
        if delta == 0:
            return 2
        if delta >= 500:
            return 0
        if delta >= 1:
            return 2
        return int(numpy.abs(numpy.log10(delta))) + 3

    return getPrecision(plot.getXAxis()), getPrecision(plot.getYAxis())


class _PointWithValue(roi_items.PointROI):
    NAME = roi_items.PointROI.NAME + " (with value)"

    def __init__(self, parent=None):
        super(_PointWithValue, self).__init__(parent=parent)
        self.sigRegionChanged.connect(self.__updateValue)

    def _connectToPlot(self, plot):
        roi_items.PointROI._connectToPlot(self, plot)
        self.__updateValue()

    def __updateValue(self):
        if self.parent() is None:
            return
        pos = self.getPosition()
        x, y = pos
        plot = self.parent().parent()
        xdigits, ydigits = _getAutoPrecision(plot)
        text = f"{x:.{xdigits}f},\n{y:.{ydigits}f}"
        self.setName(text)


class _VLineWithValue(roi_items.VerticalLineROI):
    NAME = roi_items.VerticalLineROI.NAME + " (with value)"

    def __init__(self, parent=None):
        super(_VLineWithValue, self).__init__(parent=parent)
        self.sigRegionChanged.connect(self.__updateValue)

    def _connectToPlot(self, plot):
        roi_items.VerticalLineROI._connectToPlot(self, plot)
        self.__updateValue()

    def __updateValue(self):
        if self.parent() is None:
            return
        x = self.getPosition()
        plot = self.parent().parent()
        xdigits, _ydigits = _getAutoPrecision(plot)
        text = f"{x:.{xdigits}f}"
        self.setName(text)


class _HLineWithValue(roi_items.HorizontalLineROI):
    NAME = roi_items.HorizontalLineROI.NAME + " (with value)"

    def __init__(self, parent=None):
        super(_HLineWithValue, self).__init__(parent=parent)
        self.sigRegionChanged.connect(self.__updateValue)

    def _connectToPlot(self, plot):
        roi_items.HorizontalLineROI._connectToPlot(self, plot)
        self.__updateValue()

    def __updateValue(self):
        if self.parent() is None:
            return
        y = self.getPosition()
        plot = self.parent().parent()
        _xdigits, ydigits = _getAutoPrecision(plot)
        text = f"{y:.{ydigits}f}"
        self.setName(text)


class MarkerAction(qt.QWidgetAction):
    def __init__(self, plot, parent, kind):
        super(MarkerAction, self).__init__(parent)

        self.__manager = roi.RegionOfInterestManager(plot)
        self.__manager.sigRoiAdded.connect(self.__roiAdded)

        assert isinstance(plot, PlotWidget)
        self._plotRef = weakref.ref(plot, WeakMethodProxy(self.__plotDestroyed))

        self.__tracking = False
        """Is the plot active items are tracked"""

        self.__useColorFromCursor = True
        """If true, force the ROI color with the colormap marker color"""

        self._item = None
        """The selected item"""

        self.setActiveItemTracking(True)

        menu = qt.QMenu(parent)
        menu.aboutToShow.connect(self.__aboutToShow)

        roiClasses = [
            _PointWithValue,
            _VLineWithValue,
            _HLineWithValue,
            roi_items.CrossROI,
            roi_items.LineROI,
            roi_items.RectangleROI,
        ]

        for roiClass in roiClasses:
            action = self.__manager.getInteractionModeAction(roiClass)
            action.setSingleShot(True)
            menu.addAction(action)

        menu.addSeparator()

        action = qt.QAction(menu)
        action.setIcon(icons.getQIcon("remove"))
        action.setText("Remove selected marker")
        action.setToolTip("Remove the selected marker")
        action.triggered.connect(self.clearCurrent)
        menu.addAction(action)
        self.__removeCurrent = action

        action = qt.QAction(menu)
        action.setIcon(icons.getQIcon("remove"))
        action.setText("Remove all markers")
        action.setToolTip("Remove all the markers")
        action.triggered.connect(self.clear)
        menu.addAction(action)
        self.__removeAll = action

        icon = icons.getQIcon("flint:icons/markers")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Profile tools")
        toolButton.setToolTip(
            "Manage the profiles to this scatter (not yet implemented)"
        )
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)

    def __roiAdded(self, roi):
        roi.setEditable(True)
        roi.setSelectable(True)
        self._updateRoiColor(roi)

    def __aboutToShow(self):
        roi = self.__manager.getCurrentRoi()
        self.__removeCurrent.setEnabled(roi is not None)
        nbRois = len(self.__manager.getRois())
        self.__removeAll.setEnabled(nbRois > 0)

    def clear(self):
        self.__manager.clear()

    def clearCurrent(self):
        roi = self.__manager.getCurrentRoi()
        if roi is not None:
            self.__manager.removeRoi(roi)
            roi.deleteLater()

    def setActiveItemTracking(self, tracking):
        """Enable/disable the tracking of the active item of the plot.

        :param bool tracking: Tracking mode
        """
        if self.__tracking == tracking:
            return
        plot = self.getPlotWidget()
        if self.__tracking:
            plot.sigActiveImageChanged.disconnect(self._activeImageChanged)
            plot.sigActiveScatterChanged.disconnect(self._activeScatterChanged)
        self.__tracking = tracking
        if self.__tracking:
            plot.sigActiveImageChanged.connect(self.__activeImageChanged)
            plot.sigActiveScatterChanged.connect(self.__activeScatterChanged)

    def setDefaultColorFromCursorColor(self, enabled):
        """Enabled/disable the use of the colormap cursor color to display the
        ROIs.

        If set, the manager will update the color of the profile ROIs using the
        current colormap cursor color from the selected item.
        """
        self.__useColorFromCursor = enabled

    def __activeImageChanged(self, previous, legend):
        """Handle plot item selection"""
        plot = self.getPlotWidget()
        item = plot.getImage(legend)
        self.setPlotItem(item)

    def __activeScatterChanged(self, previous, legend):
        """Handle plot item selection"""
        plot = self.getPlotWidget()
        item = plot.getScatter(legend)
        self.setPlotItem(item)

    def __plotDestroyed(self, ref):
        """Handle finalization of PlotWidget

        :param ref: weakref to the plot
        """
        self._plotRef = None
        self._roiManagerRef = None
        self._pendingRunners = []

    def setPlotItem(self, item):
        """Set the plot item focused by the profile manager.

        :param ~silx.gui.plot.items.Item item: A plot item
        """
        previous = self.getPlotItem()
        if previous is item:
            return
        if item is None:
            self._item = None
        else:
            item.sigItemChanged.connect(self.__itemChanged)
            self._item = weakref.ref(item)
        self._updateRoiColors()

    def getDefaultColor(self) -> qt.QColor:
        """Returns the default ROI color to use according to the given item.
        """
        color = "black"
        item = self.getPlotItem()
        if isinstance(item, items.ColormapMixIn):
            colormap = item.getColormap()
            name = colormap.getName()
            if name is not None:
                color = colors.cursorColorForColormap(name)
        color = colors.asQColor(color)
        return color

    def _updateRoiColors(self):
        """Update ROI color according to the item selection"""
        if not self.__useColorFromCursor:
            return
        color = self.getDefaultColor()
        for roi in self.__manager.getRois():
            roi.setColor(color)

    def _updateRoiColor(self, roi):
        """Update a specific ROI according to the current selected item.

        :param RegionOfInterest roi: The ROI to update
        """
        if not self.__useColorFromCursor:
            return
        color = self.getDefaultColor()
        roi.setColor(color)

    def __itemChanged(self, changeType):
        """Handle item changes.
        """
        if changeType == (items.ItemChangedType.COLORMAP):
            self._updateRoiColors()

    def getPlotItem(self):
        """Returns the item focused by the profile manager.

        :rtype: ~silx.gui.plot.items.Item
        """
        if self._item is None:
            return None
        item = self._item()
        if item is None:
            self._item = None
        return item

    def getPlotWidget(self):
        """The plot associated to the profile manager.

        :rtype: ~silx.gui.plot.PlotWidget
        """
        if self._plotRef is None:
            return None
        plot = self._plotRef()
        if plot is None:
            self._plotRef = None
        return plot
