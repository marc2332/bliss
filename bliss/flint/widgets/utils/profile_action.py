# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import pickle

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.tools.profile import manager as manager_mdl

from bliss.flint.model import flint_model
from bliss.flint.widgets import holder_widget


_logger = logging.getLogger(__name__)


class _CustomProfileManager(manager_mdl.ProfileManager):
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
                result.append((type(roi), roi.getName(), roi.getPosition()))
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
        for classObj, name, pos in rois:
            try:
                # FIXME: Make this object pickelable
                roi = classObj()
                roi.setName(name)
                roi.setPosition(pos)
                manager.addRoi(roi)
            except Exception:
                _logger.error("Error while importing ROI", exc_info=True)
                error = True

        return not error

    def __updateMenu(self):
        roi = self.__manager.getCurrentRoi()
        self.__separator.setVisible(roi is not None)
