# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional

from silx.gui import qt


class ExtendedDockWidget(qt.QDockWidget):

    windowClosed = qt.Signal()

    def __init__(self, parent: Optional[qt.QWidget] = None):
        qt.QDockWidget.__init__(self, parent=parent)

        # FIXME: I guess it exists a better way to do that?
        closeButton = self.findChild(qt.QAbstractButton, "qt_dockwidget_closebutton")
        closeButton.clicked.connect(self.__windowClosed)

    def __windowClosed(self):
        print("CLOSE")
        self.windowClosed.emit()
