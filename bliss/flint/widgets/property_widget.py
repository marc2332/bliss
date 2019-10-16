# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
from silx.gui import qt

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


class MainPropertyWidget(qt.QDockWidget):

    widgetUpdated = qt.Signal()

    def __init__(self, parent: qt.QWidget = None):
        super(MainPropertyWidget, self).__init__(parent=parent)
        self.setObjectName("scan-property-widget")
        self.setWindowTitle("Plot properties")
        self.__focusWidget = None
        self.__stack = _Stack(self)
        self.__stack.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Expanding)
        self.setWidget(self.__stack)

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):
        if hasattr(widget, "createPropertyWidget"):
            specificPropertyWidget = widget.createPropertyWidget(self)
            self.__stack.setWidget(specificPropertyWidget)
        elif widget is None:
            self.__stack.setWidget(None)
        else:
            _logger.error("Widget %s do not have propertyWidget factory", widget)
            self.__stack.setWidget(None)

        self.__focusWidget = widget
        self.widgetUpdated.emit()
