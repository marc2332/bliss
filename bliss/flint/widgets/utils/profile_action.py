# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging

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
        if kind == "image":
            for action in self.__manager.createImageActions(menu):
                menu.addAction(action)
        elif kind == "scatter":
            for action in self.__manager.createScatterActions(menu):
                menu.addAction(action)
            for action in self.__manager.createScatterSliceActions(menu):
                menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.__manager.createEditorAction(menu))
        menu.addSeparator()
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
