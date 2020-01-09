# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from silx.gui import qt


class LiveWindow(qt.QMainWindow):
    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self, parent=parent)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            self.dockOptions()
            | qt.QMainWindow.AllowNestedDocks
            | qt.QMainWindow.AllowTabbedDocks
            | qt.QMainWindow.GroupedDragging
            | qt.QMainWindow.AnimatedDocks
            # | qt.QMainWindow.VerticalTabs
        )
