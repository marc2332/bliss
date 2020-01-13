# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""This module contains dialog to edit style"""
from __future__ import annotations
from typing import Optional

import logging
import weakref

from silx.gui import qt
import silx.resources
from silx.gui import colors
from .extended_dock_widget import ExtendedDockWidget
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import style_model
from bliss.flint.model import flint_model


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
        self.__flintModel: Optional[flint_model.FlintState] = None

        # define modal buttons
        self.__options = qt.QToolButton(self)
        self.__options.setText("Options")
        self.__options.setVisible(False)

        self.__box = qt.QDialogButtonBox(self)
        types = qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        self.__box.setStandardButtons(types)
        self.__box.accepted.connect(self.accept)
        self.__box.rejected.connect(self.reject)

        layout.addWidget(self.__editor)
        layout.addStretch()
        layout.addSpacing(10)
        buttonLayout = qt.QHBoxLayout()
        buttonLayout.addWidget(self.__options)
        buttonLayout.addWidget(self.__box)
        layout.addLayout(buttonLayout)
        self.__updateEditor()

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        self.__flintModel = flintModel

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

    def __saveAsDefault(self):
        item = self.plotItem()
        if item is None:
            return
        if self.__flintModel is None:
            return
        style = self.__editor.selectedStyle()
        if isinstance(item, plot_item_model.ScatterItem):
            self.__flintModel.setDefaultScatterStyle(style)
        elif isinstance(item, plot_item_model.ImageItem):
            self.__flintModel.setDefaultImageStyle(style)

    def __updateEditor(self):
        item = self.plotItem()
        if item is None:
            editor = qt.QLabel(self)
            editor.setText("No item selected")
            self.__options.setVisible(False)
        else:
            if isinstance(
                item, (plot_item_model.ScatterItem, plot_item_model.ImageItem)
            ):
                if isinstance(item, plot_item_model.ScatterItem):
                    editor = _ScatterEditor(self)
                elif isinstance(item, plot_item_model.ImageItem):
                    editor = _ImageEditor(self)
                style = item.customStyle()
                if style is None:
                    # FIXME: The dialog have to know it is an auto style
                    style = item.getStyle()
                editor.selectStyle(style)
                self.__options.setVisible(True)
                self.__options.setPopupMode(qt.QToolButton.InstantPopup)
                menu = qt.QMenu(self)
                action = qt.QAction(self)
                action.setText("Use this style as default")
                action.setToolTip(
                    "Save this style as the default scatter style, which will be remembered next time."
                )
                action.triggered.connect(self.__saveAsDefault)
                menu.addAction(action)
                self.__options.setMenu(menu)
            else:
                editor = qt.QLabel(self)
                editor.setText("No editor for item class %s" % type(item))
                self.__options.setVisible(False)

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

        for s in style_model.FillStyle:
            self._fillStyle.addItem(s.value.name, s)
        for s in style_model.LineStyle:
            self._lineStyle.addItem(s.value.name, s)
        for s in style_model.SymbolStyle:
            self._symbolStyle.addItem(s.value.name, s)

        self._fillStyle.currentIndexChanged.connect(self.__updateWidgetLayout)
        self._lineStyle.currentIndexChanged.connect(self.__updateWidgetLayout)
        self._symbolStyle.currentIndexChanged.connect(self.__updateWidgetLayout)

        colorList = [
            ("No color", None),
            ("Black", (0, 0, 0)),
            ("White", (255, 255, 255)),
        ]

        for name, color in colorList:
            if color is None:
                qcolor = None
            else:
                qcolor = qt.QColor(color[0], color[1], color[2])
            self._lineColor.addColor(name, qcolor)
            self._symbolColor.addColor(name, qcolor)

    def __updateWidgetLayout(self):
        filled = self._fillStyle.currentData() != style_model.FillStyle.NO_FILL
        self._fillColormap.setVisible(filled)
        self._fillColormapLabel.setVisible(filled)

        lined = self._lineStyle.currentData() != style_model.LineStyle.NO_LINE
        self._lineColor.setVisible(lined)
        self._lineColorLabel.setVisible(lined)
        self._lineWidth.setVisible(lined)
        self._lineWidthLabel.setVisible(lined)

        symboled = self._symbolStyle.currentData() != style_model.SymbolStyle.NO_SYMBOL
        self._symbolColormap.setVisible(not filled)
        self._symbolColormapLabel.setVisible(not filled)
        self._symbolColor.setVisible(filled and symboled)
        self._symbolColorLabel.setVisible(filled and symboled)
        self._symbolSize.setVisible(symboled)
        self._symbolSizeLabel.setVisible(symboled)

        # Do it once, avoid blinking
        self.updateGeometry()

    def selectStyle(self, style: plot_model.Style):
        colormap = colors.Colormap(style.colormapLut)
        self._fillColormap.setCurrentLut(colormap)
        self._symbolColormap.setCurrentLut(colormap)
        self._selectElseInsert(self._fillStyle, style.fillStyle)
        lineColor = style.lineColor
        if lineColor is not None:
            lineColor = qt.QColor(*lineColor)
        self._selectElseInsert(self._lineColor, lineColor)
        self._selectElseInsert(self._lineStyle, style.lineStyle)
        symbolColor = style.symbolColor
        if symbolColor is not None:
            symbolColor = qt.QColor(*symbolColor)
        self._selectElseInsert(self._symbolColor, symbolColor)
        self._selectElseInsert(self._symbolStyle, style.symbolStyle)
        value = style.symbolSize if style.symbolSize is not None else 0
        self._symbolSize.setValue(value)
        value = style.lineWidth if style.lineWidth is not None else 0
        self._lineWidth.setValue(value)

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
        if lineColor is not None:
            if not lineColor.isValid():
                lineColor = None
            else:
                lineColor = lineColor.red(), lineColor.green(), lineColor.blue()
        lineStyle = self._lineStyle.currentData()
        lineWidth = self._lineWidth.value()
        symbolColor = self._symbolColor.currentData()
        if symbolColor is not None:
            if not symbolColor.isValid():
                symbolColor = None
            else:
                symbolColor = symbolColor.red(), symbolColor.green(), symbolColor.blue()

        symbolStyle = self._symbolStyle.currentData()
        symbolSize = self._symbolSize.value()
        return style_model.Style(
            lineStyle=lineStyle,
            lineColor=lineColor,
            linePalette=None,
            lineWidth=lineWidth,
            symbolStyle=symbolStyle,
            symbolSize=symbolSize,
            symbolColor=symbolColor,
            colormapLut=colormapLut,
            fillStyle=fillStyle,
        )

    def _updateLayout(self):
        pass


class _ImageEditor(qt.QWidget):
    """Editor adapted to scatter items"""

    styleUpdated = qt.Signal()

    def __init__(self, parent=None):
        super(_ImageEditor, self).__init__(parent=parent)

        filename = silx.resources.resource_filename("flint:gui/style-editor-image.ui")
        # FIXME: remove this catch of warning when it is possible
        log = logging.getLogger("py.warnings")
        log.disabled = True
        qt.loadUi(filename, self)
        log.disabled = False

    def selectStyle(self, style: plot_model.Style):
        colormap = colors.Colormap(style.colormapLut)
        self._colormap.setCurrentLut(colormap)

    def _getColormapName(self):
        return self._colormap.getCurrentName()

    def selectedStyle(self) -> plot_model.Style:
        """Returns the current selected type"""
        colormapLut = self._getColormapName()
        return style_model.Style(colormapLut=colormapLut)

    def _updateLayout(self):
        pass
