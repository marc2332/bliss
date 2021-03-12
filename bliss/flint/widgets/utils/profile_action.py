# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import pickle
import functools
import numpy
import silx.gui.plot.tools.roi as roiMdl

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.tools.profile import manager as manager_mdl

from bliss.flint.model import flint_model
from bliss.flint.widgets import holder_widget
from silx.gui.plot.tools.profile.rois import _ProfileCrossROI
from silx.gui.plot.items.roi import HorizontalLineROI, VerticalLineROI, LineROI


_logger = logging.getLogger(__name__)


class _CustomRoiManager(roiMdl.RegionOfInterestManager):
    def _feedContextMenu(self, menu):
        plot = self.parent()
        image = plot.getActiveImage()
        scatter = plot.getActiveScatter()
        item = image or scatter
        if item is not None:
            roi = self.getCurrentRoi()
            if roi is not None:
                if roi.isEditable():
                    centerAction = qt.QAction(menu)
                    centerAction.setText("Center %s" % roi.getName())
                    callback = functools.partial(self.centerRoi, roi)
                    centerAction.triggered.connect(callback)
                    menu.addAction(centerAction)

        super(_CustomRoiManager, self)._feedContextMenu(menu)

    def centerRoi(self, roi):
        plot = self.parent()
        image = plot.getActiveImage()
        scatter = plot.getActiveScatter()
        item = image or scatter
        if item is None:
            return
        bounds = item.getBounds()
        if bounds is None:
            return
        midx = (bounds[1] - bounds[0]) * 0.5
        midy = (bounds[3] - bounds[2]) * 0.5

        if isinstance(roi, _ProfileCrossROI):
            roi.setPosition((midx, midy))
        elif isinstance(roi, HorizontalLineROI):
            roi.setPosition(midy)
        elif isinstance(roi, VerticalLineROI):
            roi.setPosition(midx)
        elif isinstance(roi, LineROI):
            p1, p2 = roi.getEndPoints()
            center = (p1 + p2) * 0.5
            mid = numpy.array((midx, midy))
            p1, p2 = p1 - center + mid, p2 - center + mid
            roi.setEndPoints(p1, p2)
        else:
            _logger.error("Unsupported centering of ROI kind %s", type(roi))


class _CustomProfileManager(manager_mdl.ProfileManager):
    def __init__(self, parent=None, plot=None, roiManager=None):
        assert roiManager is None
        super(_CustomProfileManager, self).__init__(
            parent=parent, plot=plot, roiManager=_CustomRoiManager(plot)
        )

    def flintModel(self):
        flintModel = self.getPlotWidget().parent().parent().parent().flintModel()
        assert isinstance(flintModel, flint_model.FlintState)
        return flintModel

    def createProfileWindow(self, plot, roi):
        """Override to allocate a dock to hold the profile"""
        manager = self.flintModel().mainManager()
        dock = manager.allocateProfileDock()
        return dock.profileWindow()

    def initProfileWindow(self, profileWindow, roi):
        """Override the method to skip the setup of the window"""
        profileWindow.prepareWidget(roi)
        profileWindow.adjustSize()

    def clearProfileWindow(self, profileWindow):
        """Override the method to release the dock"""
        profileWindow.setProfile(None)
        workspace = self.flintModel().workspace()
        for dock in workspace.widgets():
            if not isinstance(dock, holder_widget.ProfileHolderWidget):
                continue
            if dock.profileWindow() is not profileWindow:
                continue
            dock.setUsed(False)
            return


class ProfileAction(qt.QWidgetAction):
    def __init__(self, plot, parent, kind):
        super(ProfileAction, self).__init__(parent)

        self.__manager = _CustomProfileManager(parent, plot)
        if kind == "image":
            self.__manager.setItemType(image=True)
        elif kind == "scatter":
            self.__manager.setItemType(scatter=True)
        else:
            assert False
        self.__manager.setActiveItemTracking(True)

        menu = qt.QMenu(parent)
        menu.aboutToShow.connect(self.__updateMenu)
        if kind == "image":
            for action in self.__manager.createImageActions(menu):
                menu.addAction(action)
        elif kind == "scatter":
            for action in self.__manager.createScatterActions(menu):
                menu.addAction(action)
            for action in self.__manager.createScatterSliceActions(menu):
                menu.addAction(action)
        menu.addSeparator()
        self.__editor = self.__manager.createEditorAction(menu)
        menu.addAction(self.__editor)
        self.__separator = menu.addSeparator()
        menu.addAction(self.__manager.createClearAction(menu))

        icon = icons.getQIcon("flint:icons/profile")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Profile tools")
        toolButton.setToolTip(
            "Manage the profiles to this scatter (not yet implemented)"
        )
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)

    def manager(self):
        """Returns the profile manager"""
        return self.__manager

    def getGeometry(self, roi):
        """Get a geometry from a ROI"""
        if hasattr(roi, "getPosition"):
            geometry = roi.getPosition()
        elif hasattr(roi, "getEndPoints"):
            geometry = roi.getEndPoints()
        else:
            _logger.error("Unsupported geometry for ROI %s", type(roi))
            geometry = None
        return geometry

    def setGeometry(self, roi, geometry):
        """Set a geometry to a ROI"""
        if geometry is None:
            return
        if hasattr(roi, "getPosition"):
            roi.setPosition(geometry)
        elif hasattr(roi, "getEndPoints"):
            roi.setEndPoints(*geometry)

    def saveState(self):
        """Save the profile content"""
        manager = self.manager().getRoiManager()
        rois = manager.getRois()
        result = []
        for roi in rois:
            if roi.getFocusProxy() is not None:
                # Skip compound ROIs
                continue
            try:
                # FIXME: Make this object pickelable
                geometry = self.getGeometry(roi)
                result.append((type(roi), roi.getName(), geometry))
            except Exception:
                _logger.error("Error while pickeling ROIs", exc_info=True)
                return None
        return pickle.dumps(result)

    def restoreState(self, state) -> bool:
        """Restore the profile content"""
        manager = self.manager().getRoiManager()
        manager.clear()
        if state is None:
            return
        try:
            rois = pickle.loads(state)
        except Exception:
            _logger.error("Error while unpickeling ROIs", exc_info=True)
            return False

        error = False
        for classObj, name, geometry in rois:
            try:
                # FIXME: Make this object pickelable
                roi = classObj()
                roi.setName(name)
                self.setGeometry(roi, geometry)
                manager.addRoi(roi)
            except Exception:
                _logger.error("Error while importing ROI", exc_info=True)
                error = True

        return not error

    def __updateMenu(self):
        roi = self.__manager.getCurrentRoi()
        self.__separator.setVisible(roi is not None)
