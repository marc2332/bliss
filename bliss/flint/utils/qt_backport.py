# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Backport from newest Qt version.

This module should be removed at one point.
"""

from silx.gui import qt

import logging

_logger = logging.getLogger(__name__)


class QTreeView(qt.QTreeView):
    """This class provides Qt 5.10 API for Qt 5.9 library
    """

    def __init__(self, *args, **kwargs):
        qt.QTreeView.__init__(self, *args, **kwargs)
        self._opened = set({})
        if not hasattr(qt.QTreeView, "isPersistentEditorOpen"):
            _logger.info("Apply backport from Qt 5.10")
            self.isPersistentEditorOpen = self._isPersistentEditorOpen
            self.openPersistentEditor = self._openPersistentEditor
            self.closePersistentEditor = self._closePersistentEditor

    def _uniqueId(self, index):
        return qt.QPersistentModelIndex(index)

    def _isPersistentEditorOpen(self, index):
        unique = self._uniqueId(index)
        return unique in self._opened

    def _openPersistentEditor(self, index):
        unique = self._uniqueId(index)
        self._opened.add(unique)
        return qt.QTreeView.openPersistentEditor(self, index)

    def _closePersistentEditor(self, index):
        unique = self._uniqueId(index)
        self._opened.remove(unique)
        return qt.QTreeView.closePersistentEditor(self, index)
