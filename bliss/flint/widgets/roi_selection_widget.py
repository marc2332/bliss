# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide a RoiSelectionWidget
"""

import typing

from silx.gui import qt
from silx.gui.plot.tools.roi import RegionOfInterestManager
from silx.gui.plot.tools.roi import RegionOfInterestTableWidget
from silx.gui.plot.items.roi import RectangleROI
from silx.gui.plot.items.roi import RegionOfInterest
from silx.gui.plot.tools.roi import RoiModeSelectorAction


class _AutoHideToolBar(qt.QToolBar):
    """A toolbar which hide itself if no actions are visible"""

    def actionEvent(self, event):
        if event.type() == qt.QEvent.ActionChanged:
            self._updateVisibility()
        return qt.QToolBar.actionEvent(self, event)

    def _updateVisibility(self):
        visible = False
        for action in self.actions():
            if action.isVisible():
                visible = True
                break
        self.setVisible(visible)


class RoiSelectionWidget(qt.QWidget):

    selectionFinished = qt.Signal(object)

    def __init__(self, plot, parent=None, kinds: typing.List[RegionOfInterest] = None):
        qt.QWidget.__init__(self, parent)
        # TODO: destroy on close
        self.plot = plot

        mode = plot.getInteractiveMode()["mode"]
        self.__previousMode = mode

        self.roiManager = RegionOfInterestManager(plot)
        self.roiManager.setColor("pink")
        self.roiManager.sigRoiAdded.connect(self.__roiAdded)
        self.table = RegionOfInterestTableWidget()

        # Hide coords
        horizontalHeader = self.table.horizontalHeader()
        horizontalHeader.setSectionResizeMode(0, qt.QHeaderView.Stretch)
        horizontalHeader.hideSection(3)
        self.table.setRegionOfInterestManager(self.roiManager)

        if kinds is None:
            kinds = [RectangleROI]

        self.roiToolbar = qt.QToolBar(self)
        firstAction = None
        for roiKind in kinds:
            action = self.roiManager.getInteractionModeAction(roiKind)
            action.setSingleShot(True)
            self.roiToolbar.addAction(action)
            if firstAction is None:
                firstAction = action

        applyAction = qt.QAction(self.roiManager)
        applyAction.setText("Apply")
        applyAction.triggered.connect(self.on_apply)
        applyAction.setObjectName("roi-apply-selection")
        self.roiToolbar.addSeparator()
        self.roiToolbar.addAction(applyAction)

        roiEditToolbar = _AutoHideToolBar(self)
        modeSelectorAction = RoiModeSelectorAction(self)
        modeSelectorAction.setRoiManager(self.roiManager)
        roiEditToolbar.addAction(modeSelectorAction)
        self.roiEditToolbar = roiEditToolbar

        layout = qt.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.roiToolbar)
        layout.addWidget(self.roiEditToolbar)
        layout.addWidget(self.table)

        if firstAction is not None:
            firstAction.trigger()

    def on_apply(self):
        self.selectionFinished.emit(self.roiManager.getRois())
        self.clear()

    def clear(self):
        self.roiManager.clear()
        try:
            self.plot.setInteractiveMode(self.__previousMode)
        except Exception:
            # In case the mode is not supported
            pass

    def searchForFreeName(self, roi):
        """Returns a new name for a ROI.

        The name is picked in order to match roi_counters and
        roi2spectrum_counters. It was decided to allow to have the same sub
        names for both Lima devices.

        As this module is generic, it would be better to move this code in more
        specific place.
        """
        rois = self.roiManager.getRois()
        roiNames = set([r.getName() for r in rois])

        for i in range(1, 1000):
            name = f"roi{i}"
            if name not in roiNames:
                return name
        return "roi666.666"

    def __roiAdded(self, roi):
        roi.setSelectable(True)
        roi.setEditable(True)
        if not roi.getName():
            name = self.searchForFreeName(roi)
            roi.setName(name)

    def add_roi(self, roi):
        self.roiManager.addRoi(roi)
