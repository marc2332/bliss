# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import numpy

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.tools import roi
from silx.gui.plot.items import roi as roi_items


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
        roi.setColor("black")

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