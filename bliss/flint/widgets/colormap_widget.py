# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""This module contains a shared dialog to edit colormap"""

from __future__ import annotations
from typing import Optional

import weakref
import logging

from silx.gui import qt
from silx.gui.dialog.ColormapDialog import ColormapDialog
from bliss.flint.model import scan_model
from .extended_dock_widget import ExtendedDockWidget

_logger = logging.getLogger(__name__)


class ColormapWidget(ExtendedDockWidget):
    def __init__(self, parent=None):
        super(ColormapWidget, self).__init__(parent=parent)

        dialog = ColormapDialog(parent=self)
        dialog.setWindowFlags(qt.Qt.Widget)
        dialog.setFixedSize(qt.QWIDGETSIZE_MAX, qt.QWIDGETSIZE_MAX)
        dialog.setVisible(True)
        dialog.installEventFilter(self)
        self.__dialog = weakref.ref(dialog)

        # FIXME: THis should be done with stylesheet
        mainWidget = qt.QFrame(self)
        mainWidget.setFrameShape(qt.QFrame.StyledPanel)
        mainWidget.setAutoFillBackground(True)
        layout = qt.QVBoxLayout(mainWidget)
        layout.addWidget(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        # FIXME: THis should be done with stylesheet
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(mainWidget)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

        self.__owner = None
        self.__channelName: Optional[str] = None
        self.__scan: Optional[scan_model.Scan] = None

    def eventFilter(self, widget, event):
        if event.type() == qt.QEvent.HideToParent:
            self.deleteLater()
        return widget.eventFilter(widget, event)

    def setOwner(self, widget):
        """Widget owning the colormap widget"""
        self.__owner = weakref.ref(widget)

    def owner(self):
        """Widget owning the colormap widget"""
        owner = self.__owner
        if owner is not None:
            owner = owner()
        return owner

    def __dialog(self) -> ColormapDialog:
        return self.__dialog()

    def setItem(self, item):
        """Display data and colormap from a silx item"""
        dialog = self.__dialog()
        dialog.setItem(item)
        if hasattr(item, "getColormap"):
            dialog.setColormap(item.getColormap())
        else:
            dialog.setColormap(None)

    def setColormap(self, colormap):
        """Display only a colormap in the editor"""
        dialog = self.__dialog()
        dialog.setItem(None)
        dialog.setColormap(colormap)
