# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import weakref

from silx.gui import qt
from .extended_dock_widget import ExtendedDockWidget

_logger = logging.getLogger(__name__)


class _Stack(qt.QStackedWidget):
    def setWidget(self, widget: qt.QWidget):
        count = self.count()
        if count >= 1:
            w = self.widget(0)
            self.removeWidget(w)
            w.setParent(None)
        self.addWidget(widget)

    def sizeHint(self):
        return qt.QSize(200, 500)


class MainPropertyWidget(ExtendedDockWidget):

    widgetUpdated = qt.Signal()

    def __init__(self, parent: qt.QWidget = None):
        super(MainPropertyWidget, self).__init__(parent=parent)
        self.setWindowTitle("Plot properties")
        self.__focusWidget = None
        self.__view = None
        self.__viewSource = None
        self.__stack = _Stack(self)
        self.__stack.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding)

        # Try to improve the look and feel
        # FIXME: THis should be done with stylesheet
        frame = qt.QFrame(self)
        frame.setFrameShape(qt.QFrame.StyledPanel)
        layout = qt.QVBoxLayout(frame)
        layout.addWidget(self.__stack)
        layout.setContentsMargins(0, 0, 0, 0)
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(frame)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

        self.__stack.setWidget(self.createEmptyWidget(self))

    def createEmptyWidget(self, parent: qt.QWidget):
        html = """<html>
<head/><body>
<p><span style=" font-size:14pt; font-weight:600; color:#939393;">Click on a plot</span></p>
<p><span style=" font-size:14pt; font-weight:600; color:#939393;">to display here</span></p>
<p><span style=" font-size:14pt; font-weight:600; color:#939393;">its properties</span></p>
</body></html>"""
        widget = qt.QLabel(parent)
        widget.setWordWrap(True)
        widget.setText(html)
        widget.setAlignment(qt.Qt.AlignHCenter | qt.Qt.AlignVCenter)
        return widget

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):

        viewSource = None
        if self.__viewSource is not None:
            viewSource = self.__viewSource()

        if widget is viewSource:
            # Skip if it is the same source
            if widget is None and self.__viewSource is None:
                # Make sure the view source ref is None
                # And not only invalidated
                return

        if widget is None:
            view = self.createEmptyWidget(self)
            self.__viewSource = None
        else:
            view = widget.createPropertyWidget(self)
            self.__viewSource = weakref.ref(widget)

        self.__view = view
        self.__stack.setWidget(view)
        self.__focusWidget = widget
        self.widgetUpdated.emit()
