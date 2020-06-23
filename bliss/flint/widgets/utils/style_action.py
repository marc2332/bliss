# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import weakref

from silx.gui.plot.actions import PlotAction

from bliss.flint.widgets.style_dialog import StyleDialogEditor
from bliss.flint.widgets.style_dialog import FlintColormapDialog
from bliss.flint.helper import model_helper
from bliss.flint.model import style_model
from . import plot_helper


_logger = logging.getLogger(__name__)


class FlintItemStyleAction(PlotAction):
    def __init__(self, plot, parent=None):
        self._dialog = None  # To store an instance of ColormapDialog
        super(FlintItemStyleAction, self).__init__(
            plot,
            icon="flint:icons/style",
            text="Style",
            tooltip="Edit the style of this item",
            triggered=self._actionTriggered,
            checkable=False,
            parent=parent,
        )
        self.__flintModel = None
        self.__item = None
        self.plot.sigSelectionChanged.connect(self._itemChanged)
        self._itemChanged(self.plot.currentItem(), None)

    def setFlintModel(self, flintModel):
        self.__flintModel = flintModel

    def _itemChanged(self, item, previous):
        if not isinstance(item, plot_helper.FlintItemMixIn):
            item = None
        if item is None:
            self.__item = None
        else:
            self.__item = weakref.ref(item)
        self.setEnabled(item is not None)

    def getItem(self):
        if self.__item is None:
            return None
        item = self.__item()
        if item is None:
            self.__item = None
        return item

    def _actionTriggered(self, checked=False):
        plotItem = self.getItem()
        if plotItem is None:
            return
        item = plotItem.customItem()
        if item is None:
            return
        dialog = StyleDialogEditor(self.plot)
        dialog.setPlotItem(item)
        dialog.setFlintModel(self.__flintModel)
        result = dialog.exec_()
        if result:
            style = dialog.selectedStyle()
            item.setCustomStyle(style)


class FlintItemContrastAction(PlotAction):
    def __init__(self, plot, parent=None):
        self._dialog = None  # To store an instance of ColormapDialog
        super(FlintItemContrastAction, self).__init__(
            plot,
            icon="flint:icons/contrast",
            text="Contrast",
            tooltip="Edit the contrast of this item",
            triggered=self._actionTriggered,
            checkable=False,
            parent=parent,
        )
        self.__flintModel = None
        self.__item = None
        self.plot.sigSelectionChanged.connect(self._itemChanged)
        self._itemChanged(self.plot.currentItem(), None)

    def setFlintModel(self, flintModel):
        self.__flintModel = flintModel

    def _itemChanged(self, item, previous):
        if not isinstance(item, plot_helper.FlintItemMixIn):
            item = None
        if item is None:
            self.__item = None
        else:
            self.__item = weakref.ref(item)
        self.setEnabled(item is not None)

    def getItem(self):
        if self.__item is None:
            return None
        item = self.__item()
        if item is None:
            self.__item = None
        return item

    def _actionTriggered(self, checked=False):
        plotItem = self.getItem()
        if plotItem is None:
            return
        item = plotItem.customItem()
        if item is None:
            return

        scan = plotItem.scan()
        item.customStyle()

        style = item.getStyle(scan)
        colormap = model_helper.getColormapFromItem(item, style)

        saveCustomStyle = item.customStyle()
        saveColormap = item.colormap().copy()

        def updateCustomStyle():
            style = item.getStyle(scan)
            style = style_model.Style(colormapLut=colormap.getName(), style=style)
            item.setCustomStyle(style)

        colormap.sigChanged.connect(updateCustomStyle)
        try:
            dialog = FlintColormapDialog(self.plot)
            dialog.setModal(True)
            dialog.setPlotItem(item, scan)
            dialog.setColormap(colormap)
            result = dialog.exec_()
            if result:
                style = item.customStyle()
                style = style_model.Style(colormapLut=colormap.getName(), style=style)
                item.setCustomStyle(style)
            else:
                item.setCustomStyle(saveCustomStyle)
                item.colormap().setFromColormap(saveColormap)
        finally:
            colormap.sigChanged.disconnect(updateCustomStyle)
