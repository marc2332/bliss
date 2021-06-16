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
import logging
import functools
import re

from silx.gui import qt
from silx.gui import icons
from silx.gui import utils as qtutils
from silx.gui.plot.tools.roi import RegionOfInterestManager
from silx.gui.plot.tools.roi import RegionOfInterestTableWidget
from silx.gui.plot.items.roi import RectangleROI
from silx.gui.plot.items.roi import RegionOfInterest
from silx.gui.plot.tools.roi import RoiModeSelectorAction


_logger = logging.getLogger(__name__)


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


class _RegionOfInterestManagerWithContextMenu(RegionOfInterestManager):

    sigRoiContextMenuRequested = qt.Signal(object, qt.QMenu)

    def _feedContextMenu(self, menu):
        RegionOfInterestManager._feedContextMenu(self, menu)
        roi = self.getCurrentRoi()
        if roi is not None:
            if roi.isEditable():
                self.sigRoiContextMenuRequested.emit(roi, menu)

    def getRoiByName(self, name):
        for r in self.getRois():
            if r.getName() == name:
                return r
        return None


class RoiSelectionWidget(qt.QWidget):

    selectionFinished = qt.Signal(object)

    def __init__(self, plot, parent=None, kinds: typing.List[RegionOfInterest] = None):
        qt.QWidget.__init__(self, parent)
        # TODO: destroy on close
        self.plot = plot

        mode = plot.getInteractiveMode()["mode"]
        self.__previousMode = mode

        self.roiManager = _RegionOfInterestManagerWithContextMenu(plot)
        self.roiManager.setColor("pink")
        self.roiManager.sigRoiAdded.connect(self.__roiAdded)
        self.roiManager.sigRoiContextMenuRequested.connect(self.roiContextMenuRequested)
        self.roiManager.sigCurrentRoiChanged.connect(self.__currentRoiChanged)
        self.table = RegionOfInterestTableWidget(self)

        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        selectionModel = self.table.selectionModel()
        selectionModel.currentRowChanged.connect(self.__currentRowChanged)

        # Hide coords
        horizontalHeader = self.table.horizontalHeader()
        horizontalHeader.setSectionResizeMode(0, qt.QHeaderView.Stretch)
        horizontalHeader.hideSection(1)  # is editable
        horizontalHeader.hideSection(3)  # coords
        self.table.setRegionOfInterestManager(self.roiManager)

        if kinds is None:
            kinds = [RectangleROI]

        self.roiToolbar = qt.QToolBar(self)

        cloneAction = qt.QAction(self.roiManager)
        cloneAction.setText("Duplicate")
        cloneAction.setToolTip("Duplicate selected ROI")
        icon = icons.getQIcon("flint:icons/roi-duplicate")
        cloneAction.setIcon(icon)
        cloneAction.setEnabled(False)
        cloneAction.triggered.connect(self.cloneCurrentRoiRequested)
        self.__cloneAction = cloneAction

        renameAction = qt.QAction(self.roiManager)
        renameAction.setText("Rename")
        renameAction.setToolTip("Rename selected ROI")
        icon = icons.getQIcon("flint:icons/roi-rename")
        renameAction.setIcon(icon)
        renameAction.setEnabled(False)
        renameAction.triggered.connect(self.renameCurrentRoiRequested)
        self.__renameAction = renameAction

        self.roiToolbar.addAction(cloneAction)
        self.roiToolbar.addAction(renameAction)
        self.roiToolbar.addSeparator()

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
        self.addAction(applyAction)

        self.applyButton = qt.QPushButton(self)
        self.applyButton.setFixedHeight(40)
        self.applyButton.setText("Apply this ROIs")
        icon = icons.getQIcon("flint:icons/roi-save")
        self.applyButton.setIcon(icon)
        self.applyButton.clicked.connect(self.on_apply)
        self.applyButton.setIconSize(qt.QSize(24, 24))

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
        layout.addWidget(self.applyButton)

        if firstAction is not None:
            firstAction.trigger()

    def __currentRowChanged(self, current, previous):
        model = self.table.model()
        index = model.index(current.row(), 0)
        name = model.data(index)
        roi = self.roiManager.getRoiByName(name)
        self.roiManager.setCurrentRoi(roi)

    def __currentRoiChanged(self, roi):
        selectionModel = self.table.selectionModel()
        if roi is None:
            selectionModel.clear()
            enabled = False
        else:
            name = roi.getName()
            model = self.table.model()
            for row in range(model.rowCount()):
                index = model.index(row, 0)
                if model.data(index) == name:
                    selectionModel.reset()
                    mode = (
                        qt.QItemSelectionModel.Clear
                        | qt.QItemSelectionModel.Rows
                        | qt.QItemSelectionModel.Current
                        | qt.QItemSelectionModel.Select
                    )
                    selectionModel.select(index, mode)
                    enabled = True
                    break
            else:
                selectionModel.clear()
                enabled = False

        self.__cloneAction.setEnabled(enabled)
        self.__renameAction.setEnabled(enabled)

    def on_apply(self):
        self.selectionFinished.emit(self.roiManager.getRois())
        self.clear()

    def roiContextMenuRequested(self, roi, menu: qt.QMenu):
        menu.addSeparator()

        cloneAction = qt.QAction(menu)
        cloneAction.setText("Duplicate %s" % roi.getName())
        callback = functools.partial(self.cloneRoiRequested, roi)
        cloneAction.triggered.connect(callback)
        menu.addAction(cloneAction)

        renameAction = qt.QAction(menu)
        renameAction.setText("Rename %s" % roi.getName())
        callback = functools.partial(self.renameRoiRequested, roi)
        renameAction.triggered.connect(callback)
        menu.addAction(renameAction)

    def renameRoiRequested(self, roi):
        name = roi.getName()
        result = qt.QInputDialog.getText(
            self, "Rename ROI name", "ROI name", qt.QLineEdit.Normal, name
        )
        if result[1]:
            newName = result[0]
            if newName == name:
                return
            if self.isAlreadyUsed(newName):
                qt.QMessageBox.warning(
                    self, "Action cancelled", f"ROI name '{newName}' already used."
                )
                return
            roi.setName(newName)

    def __splitTrailingNumber(self, name):
        m = re.search(r"^(.*?)(\d+)$", name)
        if m is None:
            return name, 1
        groups = m.groups()
        return groups[0], int(groups[1])

    def cloneRoiRequested(self, roi):
        name = roi.getName()
        basename, number = self.__splitTrailingNumber(name)
        for _ in range(50):
            number = number + 1
            name = f"{basename}{number}"
            if not self.isAlreadyUsed(name):
                break

        result = qt.QInputDialog.getText(
            self, "Clone ROI", "ROI name", qt.QLineEdit.Normal, name
        )
        if result[1]:
            if self.isAlreadyUsed(name):
                qt.QMessageBox.warning(
                    self, "Action cancelled", f"ROI name '{name}' already used."
                )
                return

            try:
                newRoi = roi.clone()
            except Exception:
                _logger.error("Error while cloning ROI", exc_info=True)
                return

            newName = result[0]
            newRoi.setName(newName)
            self.roiManager.addRoi(newRoi)

    def isAlreadyUsed(self, name):
        for r in self.roiManager.getRois():
            if r.getName() == name:
                return True
        return False

    def cloneCurrentRoiRequested(self):
        roi = self.roiManager.getCurrentRoi()
        if roi is None:
            return
        self.cloneRoiRequested(roi)

    def renameCurrentRoiRequested(self):
        roi = self.roiManager.getCurrentRoi()
        if roi is None:
            return
        self.renameRoiRequested(roi)

    def clear(self):
        roiManager = self.roiManager
        if len(roiManager.getRois()) > 0:
            # Weird: At this level self.table can be already deleted in C++ side
            # The if rois > 0 is a work around
            selectionModel = self.table.selectionModel()
            with qtutils.blockSignals(selectionModel):
                roiManager.clear()

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
