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


class MainPropertyWidget(qt.QDockWidget):

    widgetUpdated = qt.Signal()

    def __init__(self, parent: qt.QWidget = None):
        super(MainPropertyWidget, self).__init__(parent=parent)
        self.setObjectName("scan-property-widget")
        self.setWindowTitle("Plot properties")
        self.__focusWidget = None

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):
        if hasattr(widget, "createPropertyWidget"):
            specificPropertyWidget = widget.createPropertyWidget(self)
            self.setWidget(specificPropertyWidget)
        elif widget is None:
            self.setWidget(None)
        else:
            _logger.error("Widget %s do not have propertyWidget factory", widget)
            self.setWidget(None)

        self.__focusWidget = widget
        self.widgetUpdated.emit()
