# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""This module contains dialog to edit style"""
from __future__ import annotations
from typing import Optional
from typing import Tuple
from typing import Dict
from typing import List

import logging
import weakref

from silx.gui import qt
import silx.resources
from silx.gui import colors
from .extended_dock_widget import ExtendedDockWidget
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import style_model


class StyleDock(ExtendedDockWidget):
    def __init__(self, parent: Optional[qt.QWidget] = None):
        ExtendedDockWidget.__init__(self, parent=parent)
        widget = StyleDialogEditor(parent=self)
        self.setWidget(widget)


class StyleDialogEditor(qt.QDialog):
    def __init__(self, parent=None):
        super(StyleDialogEditor, self).__init__(parent=parent)
        self.setWindowTitle("Style editor")
        layout = qt.QVBoxLayout(self)
        self.setLayout(layout)

        self.__item = None
        self.__editor = qt.QWidget(self)

        # define modal buttons
        self.__box = qt.QDialogButtonBox(self)
        types = qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        self.__box.setStandardButtons(types)
        self.__box.accepted.connect(self.accept)
        self.__box.rejected.connect(self.reject)

        layout.addWidget(self.__editor)
        layout.addStretch()
        layout.addSpacing(10)
        layout.addWidget(self.__box)
        self.__updateEditor()

    def setPlotItem(self, item: plot_model.Item):
        self.__item = weakref.ref(item)
        self.__updateEditor()

    def plotItem(self) -> Optional[plot_model.Item]:
        if self.__item is None:
            return None
        item = self.__item()
        if item is None:
            self.__item = None
        return item

    def __updateEditor(self):
        item = self.plotItem()
        if item is None:
            editor = qt.QLabel(self)
            editor.setText("No item selected")
        else:
            if isinstance(item, plot_item_model.ScatterItem):
                editor = _ScatterEditor(self)
                style = item.customStyle()
                if style is None:
                    # FIXME: The dialog have to know it is an auto style
                    style = item.getStyle()
                editor.selectStyle(style)
            else:
                editor = qt.QLabel(self)
                editor.setText("No editor for item class %s" % type(item))

        layout = self.layout()
        layout.replaceWidget(self.__editor, editor)
        self.__editor.setVisible(False)
        self.__editor.setParent(None)
        self.__editor.deleteLater()
        self.__editor = editor

    def selectedStyle(self) -> plot_model.Style:
        """Returns the current selected type"""
        if not hasattr(self.__editor, "selectedStyle"):
            return None
        return self.__editor.selectedStyle()


class _ScatterEditor(qt.QWidget):
    """Editor adapted to scatter items"""

    styleUpdated = qt.Signal()

    def __init__(self, parent=None):
        super(_ScatterEditor, self).__init__(parent=parent)

        filename = silx.resources.resource_filename("flint:gui/style-editor-scatter.ui")
        # FIXME: remove this catch of warning when it is possible
        log = logging.getLogger("py.warnings")
        log.disabled = True
        qt.loadUi(filename, self)
        log.disabled = False

        traduction = {}
        traduction[style_model.FillStyle.NO_FILL] = "No fill"
        traduction[style_model.FillStyle.SCATTER_INTERPOLATION] = "Interpolation"
        traduction[style_model.FillStyle.SCATTER_REGULAR_GRID] = "Regular grid"
        traduction[style_model.FillStyle.SCATTER_IRREGULAR_GRID] = "Irregular grid"
        traduction[style_model.LineStyle.NO_LINE] = "No line"
        traduction[style_model.LineStyle.SCATTER_SEQUENCE] = "Sequence of points"
        traduction[None] = "No symbols"
        traduction["o"] = "Circle"
        traduction["+"] = "Cross"

        for s in style_model.FillStyle:
            self._fillStyle.addItem(traduction[s], s)
        for s in style_model.LineStyle:
            self._lineStyle.addItem(traduction[s], s)
        for s in [None, "o", "+"]:
            self._symbolStyle.addItem(traduction[s], s)

        self._fillStyle.currentIndexChanged.connect(self.__updateWidgetLayout)
        self._lineStyle.currentIndexChanged.connect(self.__updateWidgetLayout)
        self._symbolStyle.currentIndexChanged.connect(self.__updateWidgetLayout)

        self._lineColor.addItem("No color", None)
        self._lineColor.addItem("Black", (0, 0, 0))
        self._lineColor.addItem("White", (255, 255, 255))

        self._symbolColor.addItem("No color", None)
        self._symbolColor.addItem("Black", (0, 0, 0))
        self._symbolColor.addItem("White", (255, 255, 255))

    def __updateWidgetLayout(self):
        filled = self._fillStyle.currentData() != style_model.FillStyle.NO_FILL
        self._fillColormap.setVisible(filled)
        self._fillColormapLabel.setVisible(filled)

        lined = self._lineStyle.currentData() != style_model.LineStyle.NO_LINE
        self._lineColor.setVisible(lined)
        self._lineColorLabel.setVisible(lined)
        self._lineWidth.setVisible(lined)
        self._lineWidthLabel.setVisible(lined)

        symboled = self._symbolStyle.currentData() is not None
        self._symbolColormap.setVisible(not filled)
        self._symbolColormapLabel.setVisible(not filled)
        self._symbolColor.setVisible(filled and symboled)
        self._symbolColorLabel.setVisible(filled and symboled)
        self._symbolSize.setVisible(lined)
        self._symbolSizeLabel.setVisible(lined)

    def selectStyle(self, style: plot_model.Style):
        colormap = colors.Colormap(style.colormapLut)
        self._fillColormap.setCurrentLut(colormap)
        self._symbolColormap.setCurrentLut(colormap)
        self._selectElseInsert(self._fillStyle, style.fillStyle)
        self._selectElseInsert(self._lineColor, style.lineColor)
        self._selectElseInsert(self._lineStyle, style.lineStyle)
        self._selectElseInsert(self._symbolColor, style.symbolColor)
        self._selectElseInsert(self._symbolStyle, style.symbolStyle)
        self._symbolSize.setValue(style.symbolSize)
        self.__updateWidgetLayout()

    def _getColormapName(self):
        fillStyle = self._fillStyle.currentData()
        if fillStyle not in [None, style_model.FillStyle.NO_FILL]:
            return self._fillColormap.getCurrentName()
        else:
            return self._symbolColormap.getCurrentName()

    def _selectElseInsert(self, comboBox: qt.QComboBox, value):
        for index in range(comboBox.count()):
            if value == comboBox.itemData(index):
                comboBox.setCurrentIndex(index)
                return
        if value is None:
            # If None was not a value
            comboBox.setCurrentIndex(-1)
            return
        comboBox.addItem(str(value), value)
        comboBox.setCurrentIndex(comboBox.count() - 1)

    def selectedStyle(self) -> plot_model.Style:
        """Returns the current selected type"""
        fillStyle = self._fillStyle.currentData()
        colormapLut = self._getColormapName()
        lineColor = self._lineColor.currentData()
        lineStyle = self._lineStyle.currentData()
        # FIXME: not supported
        lineWidth = self._lineWidth.value()
        symbolColor = self._symbolColor.currentData()
        symbolStyle = self._symbolStyle.currentData()
        symbolSize = self._symbolSize.value()
        return style_model.Style(
            lineStyle=lineStyle,
            lineColor=lineColor,
            linePalette=None,
            symbolStyle=symbolStyle,
            symbolSize=symbolSize,
            symbolColor=symbolColor,
            colormapLut=colormapLut,
            fillStyle=fillStyle,
        )

    def _updateLayout(self):
        pass
