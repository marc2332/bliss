# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide a RoiSelectionWidget
"""

from silx.gui import qt
from silx.gui.plot.tools.roi import RegionOfInterestManager
from silx.gui.plot.tools.roi import RegionOfInterestTableWidget
from silx.gui.plot.items.roi import RectangleROI


class RoiSelectionWidget(qt.QMainWindow):

    selectionFinished = qt.Signal(object)

    def __init__(self, plot, parent=None):
        qt.QMainWindow.__init__(self, parent)
        # TODO: destroy on close
        self.plot = plot
        panel = qt.QWidget()
        self.setCentralWidget(panel)

        mode = plot.getInteractiveMode()["mode"]
        self.__previousMode = mode

        self.roi_manager = RegionOfInterestManager(plot)
        self.roi_manager.setColor("pink")
        self.roi_manager.sigRoiAdded.connect(self.on_added)
        self.table = RegionOfInterestTableWidget()
        self.table.setRegionOfInterestManager(self.roi_manager)

        self.toolbar = qt.QToolBar()
        self.addToolBar(self.toolbar)
        rectangle_action = self.roi_manager.getInteractionModeAction(RectangleROI)
        rectangle_action.setObjectName("roi-select-rectangle")
        self.toolbar.addAction(rectangle_action)

        self.toolbar.addSeparator()
        apply_action = qt.QAction(self.roi_manager)
        apply_action.setText("Apply")
        apply_action.triggered.connect(self.on_apply)
        apply_action.setObjectName("roi-apply-selection")
        self.toolbar.addAction(apply_action)

        layout = qt.QVBoxLayout(panel)
        layout.addWidget(self.table)

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

    def on_added(self, roi):
        if not roi.getLabel():
            nb_rois = len(self.roi_manager.getRois())
            roi.setLabel("roi{}".format(nb_rois))

    def add_roi(self, roi):
        self.roi_manager.addRoi(roi)
