# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import typing

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.tools import roi
from silx.gui.plot.items import roi as roi_items


class _PointWithValue(roi_items.PointROI):
    def __init__(self, parent=None):
        super(_PointWithValue, self).__init__(parent=parent)
        self.sigRegionChanged.connect(self.__updateValue)

    def _connectToPlot(self, plot):
        roi_items.PointROI._connectToPlot(self, plot)
        self.__updateValue()

    def __updateValue(self):
        pos = self.getPosition()
        # FIXME: Improve the digit according to the plot range
        text = "%.3f,\n  %.3f" % (pos[0], pos[1])
        self.setName(text)


class _VLineWithValue(roi_items.VerticalLineROI):
    def __init__(self, parent=None):
        super(_VLineWithValue, self).__init__(parent=parent)
        self.sigRegionChanged.connect(self.__updateValue)

    def _connectToPlot(self, plot):
        roi_items.VerticalLineROI._connectToPlot(self, plot)
        self.__updateValue()

    def __updateValue(self):
        pos = self.getPosition()
        # FIXME: Improve the digit according to the plot range
        text = "%.3f" % pos
        self.setName(text)


class MarkerAction(qt.QWidgetAction):
    def __init__(self, plot, parent, kind):
        super(MarkerAction, self).__init__(parent)

        self.__manager = roi.RegionOfInterestManager(plot)
        self.__manager.sigRoiAdded.connect(self.__roiAdded)

        menu = qt.QMenu(parent)
        action = self.__manager.getInteractionModeAction(_PointWithValue)
        action.setSingleShot(True)
        menu.addAction(action)
        action = self.__manager.getInteractionModeAction(_VLineWithValue)
        action.setSingleShot(True)
        menu.addAction(action)
        action = self.__manager.getInteractionModeAction(roi_items.RectangleROI)
        action.setSingleShot(True)
        menu.addAction(action)

        menu.addSeparator()

        action = qt.QAction(menu)
        action.setIcon(icons.getQIcon("remove"))
        action.setText("Remove markers")
        action.setToolTip("Remove all the markers")
        action.triggered.connect(self.clear)
        menu.addAction(action)

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
        roi.setColor("black")

    def clear(self):
        self.__manager.clear()
