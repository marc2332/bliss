# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging

from silx.gui import qt
from bliss.flint.model import scan_model


_logger = logging.getLogger(__name__)


class SelectChannelDialog(qt.QDialog):
    def __init__(self, parent=None):
        super(SelectChannelDialog, self).__init__(parent=parent)
        self.setWindowTitle("Channel selection")
        layout = qt.QVBoxLayout(self)
        self.setLayout(layout)

        self.__channelNames = qt.QComboBox(self)

        self.__box = qt.QDialogButtonBox(self)
        types = qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        self.__box.setStandardButtons(types)
        self.__box.accepted.connect(self.accept)
        self.__box.rejected.connect(self.reject)

        layout.addWidget(self.__channelNames)
        layout.addWidget(self.__box)

    def setScan(self, scan: scan_model.Scan):
        self.__channelNames.clear()
        for device in scan.devices():
            for channel in device.channels():
                self.__channelNames.addItem(channel.name())
        if self.__channelNames.count() > 0:
            self.__channelNames.setCurrentIndex(0)
        else:
            self.__channelNames.setCurrentIndex(-1)

    def selectedChannelName(self) -> str:
        """Returns the selected channel name"""
        index = self.__channelNames.currentIndex()
        if index == -1:
            return None
        return self.__channelNames.currentText()
