# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
from silx.gui import qt
from .extended_dock_widget import ExtendedDockWidget

_logger = logging.getLogger(__name__)


class _Stack(qt.QStackedWidget):
    def setWidget(self, widget: qt.QWidget):
        count = self.count()
        if count >= 1:
            w = self.widget(0)
            self.removeWidget(w)
        self.addWidget(widget)

    def sizeHint(self):
        return qt.QSize(200, 500)


class MainPropertyWidget(ExtendedDockWidget):

    widgetUpdated = qt.Signal()

    def __init__(self, parent: qt.QWidget = None):
        super(MainPropertyWidget, self).__init__(parent=parent)
        self.setObjectName("scan-property-widget")
        self.setWindowTitle("Plot properties")
        self.__focusWidget = None
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
        if hasattr(widget, "createPropertyWidget"):
            specificPropertyWidget = widget.createPropertyWidget(self)
            self.__stack.setWidget(specificPropertyWidget)
        elif widget is None:
            self.__stack.setWidget(self.createEmptyWidget(self))
        else:
            _logger.error("Widget %s do not have propertyWidget factory", widget)
            self.__stack.setWidget(self.createEmptyWidget(self))

        self.__focusWidget = widget
        self.widgetUpdated.emit()
