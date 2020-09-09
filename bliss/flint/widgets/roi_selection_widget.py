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
from .utils import rois as rois_mdl


class RoiSelectionWidget(qt.QMainWindow):

    selectionFinished = qt.Signal(object)

    def __init__(self, plot, parent=None, kinds: typing.List[RegionOfInterest] = None):
        qt.QMainWindow.__init__(self, parent)
        # TODO: destroy on close
        self.plot = plot
        panel = qt.QWidget()
        self.setCentralWidget(panel)

        mode = plot.getInteractiveMode()["mode"]
        self.__previousMode = mode

        self.roi_manager = RegionOfInterestManager(plot)
        self.roi_manager.setColor("pink")
        self.roi_manager.sigRoiAdded.connect(self.__roiAdded)
        self.table = RegionOfInterestTableWidget()
        self.table.setRegionOfInterestManager(self.roi_manager)

        if kinds is None:
            kinds = [RectangleROI]

        self.toolbar = qt.QToolBar()
        self.addToolBar(self.toolbar)

        first_action = None
        for roiKind in kinds:
            action = self.roi_manager.getInteractionModeAction(roiKind)
            self.toolbar.addAction(action)
            if first_action is None:
                first_action = action

        self.toolbar.addSeparator()
        apply_action = qt.QAction(self.roi_manager)
        apply_action.setText("Apply")
        apply_action.triggered.connect(self.on_apply)
        apply_action.setObjectName("roi-apply-selection")
        self.toolbar.addAction(apply_action)

        layout = qt.QVBoxLayout(panel)
        layout.addWidget(self.table)

        if first_action is not None:
            first_action.trigger()

    def on_apply(self):
        self.selectionFinished.emit(self.roi_manager.getRois())
        self.clear()

    def clear(self):
        self.roi_manager.clear()
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
        rois = self.roi_manager.getRois()
        roiNames = set([r.getName() for r in rois])

        for i in range(1, 1000):
            name = f"roi{i}"
            if name not in roiNames:
                return name
        return "roi666.666"

    def __roiAdded(self, roi):
        if not roi.getName():
            name = self.searchForFreeName(roi)
            roi.setName(name)

    def add_roi(self, roi):
        self.roi_manager.addRoi(roi)
