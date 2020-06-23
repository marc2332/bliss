# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging

from silx.gui import qt
from silx.gui.plot.tools.profile.manager import ProfileWindow

from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget

_logger = logging.getLogger(__name__)


class ProfileHolderWidget(ExtendedDockWidget):
    """Hold a profile as a dock"""

    widgetActivated = qt.Signal(object)

    def __init__(self, parent=None):
        ExtendedDockWidget.__init__(self, parent=parent)
        profileWindow = ProfileWindow(parent=self)
        profileWindow.setWindowFlags(qt.Qt.Widget)
        profileWindow.setMinimumSize(300, 200)
        self.setWidget(profileWindow)
        self.__isUsed = False
        self.windowClosed.connect(self.__windowClosed)

    def sizeHint(self):
        return ProfileWindow.sizeHint(self)

    def __windowClosed(self):
        self.windowClosed.disconnect(self.__windowClosed)
        profileWindow = self.widget()
        profileWindow.sigClose.emit()

    def setUsed(self, used: bool):
        """Reserve or release the use of this holder"""
        self.__isUsed = used

    def isUsed(self) -> bool:
        """Returns true if display is owned by a plot"""
        return self.__isUsed

    def setFlintModel(self, model):
        pass

    def profileWindow(self):
        return self.widget()
