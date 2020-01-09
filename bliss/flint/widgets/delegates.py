# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
from typing import Dict
from typing import Callable
from typing import Optional

import logging
import numpy

from silx.gui import qt
from silx.gui.widgets.LegendIconWidget import LegendIconWidget
from silx.gui.dialog.ColormapDialog import ColormapDialog
from silx.gui import colors as silx_colors
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.model import style_model
from bliss.flint.widgets.eye_check_box import EyeCheckBox
from bliss.flint.helper import model_helper
from bliss.flint.widgets.style_dialog import StyleDialogEditor


_logger = logging.getLogger(__name__)


PlotItemRole = qt.Qt.UserRole + 100
VisibilityRole = qt.Qt.UserRole + 101
RadioRole = qt.Qt.UserRole + 102


_colormapPixmap: Dict[str, qt.QPixmap] = {}
_COLORMAP_PIXMAP_SIZE = 32


class VisibilityPropertyItemDelegate(qt.QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(VisibilityPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = EyeCheckBox(parent=parent)
        editor.toggled.connect(self.__commitData)
        state = index.data(VisibilityRole)
        editor.setChecked(state == qt.Qt.Checked)
        state = index.data(VisibilityRole)
        self.__updateEditorStyle(editor, state)
        return editor

    def __commitData(self):
        editor = self.sender()
        self.commitData.emit(editor)

    def __updateEditorStyle(self, editor: qt.QCheckBox, state: qt.Qt.CheckState):
        editor.setVisible(state is not None)

    def setEditorData(self, editor, index):
        state = index.data(VisibilityRole)
        self.__updateEditorStyle(editor, state)

    def setModelData(self, editor, model, index):
        state = qt.Qt.Checked if editor.isChecked() else qt.Qt.Unchecked
        model.setData(index, state, role=VisibilityRole)

    def updateEditorGeometry(self, editor, option, index):
        # Center the widget to the cell
        size = editor.sizeHint()
        half = size / 2
        halfPoint = qt.QPoint(half.width(), half.height() - 1)
        pos = option.rect.center() - halfPoint
        editor.move(pos)


class _RemovePlotItemButton(qt.QToolButton):
    def __init__(self, parent: qt.QWidget = None):
        super(_RemovePlotItemButton, self).__init__(parent=parent)
        self.__plotItem: Optional[plot_model.Item] = None
        self.clicked.connect(self.__requestRemoveItem)
        icon = icons.getQIcon("flint:icons/remove-item")
        self.setIcon(icon)
        self.setAutoRaise(True)

    def __requestRemoveItem(self):
        plotItem = self.__plotItem
        plot = plotItem.plot()
        if plot is not None:
            model_helper.removeItemAndKeepAxes(plot, plotItem)

    def setPlotItem(self, plotItem: plot_model.Item):
        self.__plotItem = plotItem


class RemovePropertyItemDelegate(qt.QStyledItemDelegate):
    def __init__(self, parent):
        qt.QStyledItemDelegate.__init__(self, parent=parent)

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(RemovePropertyItemDelegate, self).createEditor(
                parent, option, index
            )
        editor = _RemovePlotItemButton(parent=parent)
        plotItem = self.getPlotItem(index)
        editor.setVisible(plotItem is not None)
        return editor

    def getPlotItem(self, index) -> Union[None, plot_model.Item]:
        plotItem = index.data(PlotItemRole)
        if not isinstance(plotItem, plot_model.Item):
            return None
        return plotItem

    def setEditorData(self, editor, index):
        plotItem = self.getPlotItem(index)
        editor.setVisible(plotItem is not None)
        editor.setPlotItem(plotItem)

    def setModelData(self, editor, model, index):
        pass


class StylePropertyWidget(qt.QWidget):
    def __init__(self, parent):
        super(StylePropertyWidget, self).__init__(parent=parent)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.__legend = LegendIconWidget(self)
        layout.addWidget(self.__legend)
        layout.addSpacing(2)

        self.__buttonStyle: Optional[qt.QToolButton] = None
        self.__buttonContrast: Optional[qt.QToolButton] = None

        self.__plotItem: Union[None, plot_model.Plot] = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__scan: Union[None, scan_model.Scan] = None

    def setEditable(self, isEditable):
        """Set the widget editable.

        A button is enabled to be able to edit the style, and to propagate it to
        the item.
        """
        if self.__buttonStyle is not None:
            self.__buttonStyle.setVisible(isEditable)
        elif isEditable:
            icon = icons.getQIcon("flint:icons/style")
            self.__buttonStyle = qt.QToolButton()
            self.__buttonStyle.setToolTip("Edit the style of this item")
            self.__buttonStyle.setIcon(icon)
            self.__buttonStyle.setAutoRaise(True)
            self.__buttonStyle.clicked.connect(self.__editStyle)
            layout = self.layout()
            layout.addWidget(self.__buttonStyle)

        if self.__buttonContrast is not None:
            self.__buttonContrast.setVisible(isEditable)
        else:
            icon = icons.getQIcon("flint:icons/contrast")
            self.__buttonContrast = qt.QToolButton()
            self.__buttonContrast.setToolTip("Edit the contrast of this item")
            self.__buttonContrast.setIcon(icon)
            self.__buttonContrast.setAutoRaise(True)
            self.__buttonContrast.clicked.connect(self.__editConstrast)
            layout = self.layout()
            layout.addWidget(self.__buttonContrast)
        self.__updateEditButton()

    def __updateEditButton(self):
        if self.__buttonContrast is not None:
            visible = self.__plotItem is not None and isinstance(
                self.__plotItem,
                (plot_item_model.ImageItem, plot_item_model.ScatterItem),
            )
            self.__buttonContrast.setVisible(visible)

    def __editStyle(self):
        if self.__plotItem is None:
            return
        dialog = StyleDialogEditor(self)
        dialog.setPlotItem(self.__plotItem)
        dialog.setFlintModel(self.__flintModel)
        result = dialog.exec_()
        if result:
            style = dialog.selectedStyle()
            self.__plotItem.setCustomStyle(style)

    def __editConstrast(self):
        if self.__plotItem is None:
            return

        scan = self.__scan
        item = self.__plotItem
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

        dialog = ColormapDialog(self)
        dialog.setModal(True)

        if scan is not None:
            if isinstance(item, plot_item_model.ScatterItem):
                data = item.valueChannel().array(scan)
                dialog.setData(data)

        dialog.setColormap(colormap)
        result = dialog.exec_()
        if result:
            style = item.customStyle()
            style = style_model.Style(colormapLut=colormap.getName(), style=style)
            self.__plotItem.setCustomStyle(style)
        else:
            item.setCustomStyle(saveCustomStyle)
            item.colormap().setFromColormap(saveColormap)

    def setPlotItem(self, plotItem: plot_model.Item):
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.disconnect(self.__plotItemChanged)
        self.__plotItem = plotItem
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.connect(self.__plotItemChanged)
            self.__plotItemStyleChanged()
        self.__updateEditButton()

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
            self.__setScan(None)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)
            self.__setScan(self.__flintModel.currentScan())

    def __currentScanChanged(self):
        self.__setScan(self.__flintModel.currentScan())

    def __setScan(self, scan: Union[None, scan_model.Scan]):
        self.__scan = scan
        self.__update()

    def __plotItemChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.CUSTOM_STYLE:
            self.__plotItemStyleChanged()

    def __plotItemStyleChanged(self):
        self.__update()

    def getQColor(self, color):
        # FIXME: It would be good to use silx 0.12 colors.asQColor
        if color is None:
            return qt.QColor()
        color = silx_colors.rgba(color)
        return qt.QColor.fromRgbF(*color)

    def __updateScatter(self, style: plot_model.Style):
        pointBased = True
        if style.fillStyle is not style_model.FillStyle.NO_FILL:
            if not isinstance(style.fillStyle, str):
                pointBased = False
                self.__legend.setColormap(style.colormapLut)
            else:
                self.__legend.setColormap(None)
        else:
            self.__legend.setColormap(None)

        if style.lineStyle is not style_model.LineStyle.NO_LINE:
            self.__legend.setLineStyle("-")
            color = self.getQColor(style.lineColor)
            self.__legend.setLineColor(color)
            self.__legend.setLineWidth(1.5)
        else:
            self.__legend.setLineStyle(" ")

        if pointBased:
            if style.symbolStyle == style_model.SymbolStyle.NO_SYMBOL:
                symbolStyle = "o"
            else:
                symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
            self.__legend.setSymbol(symbolStyle)
            self.__legend.setSymbolColormap(style.colormapLut)
            self.__legend.setSymbolColor(None)
        elif style.symbolStyle is not style_model.SymbolStyle.NO_SYMBOL:
            symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
            self.__legend.setSymbol(symbolStyle)
            color = self.getQColor(style.symbolColor)
            self.__legend.setSymbolColor(color)
            self.__legend.setSymbolColormap(None)
        else:
            self.__legend.setSymbol(" ")

    def __update(self):
        plotItem = self.__plotItem
        if plotItem is None:
            self.__legend.setLineColor("red")
            self.__legend.setLineStyle(":")
            self.__legend.setLineWidth(1.5)
        else:
            scan = self.__scan
            try:
                style = plotItem.getStyle(scan)
                if isinstance(plotItem, plot_item_model.ScatterItem):
                    self.__updateScatter(style)
                else:
                    color = self.getQColor(style.lineColor)
                    if style.symbolStyle is not style_model.SymbolStyle.NO_SYMBOL:
                        symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
                        self.__legend.setSymbol(symbolStyle)
                        if style.symbolColor is None:
                            self.__legend.setSymbolColor(qt.QColor(0xE0, 0xE0, 0xE0))
                        else:
                            symbolColor = self.getQColor(style.symbolColor)
                            self.__legend.setSymbolColor(symbolColor)
                    self.__legend.setSymbolColormap(style.colormapLut)
                    if isinstance(style.lineStyle, str):
                        lineStyle = style.lineStyle
                    elif style.lineStyle == style_model.LineStyle.NO_LINE:
                        lineStyle = " "
                    elif style.lineStyle == style_model.LineStyle.SCATTER_SEQUENCE:
                        lineStyle = "-"
                    self.__legend.setLineColor(color)
                    self.__legend.setLineStyle(lineStyle)
                    self.__legend.setLineWidth(1.5)
            except Exception:
                _logger.error("Error while reaching style", exc_info=True)
                self.__legend.setLineColor("grey")
                self.__legend.setLineStyle(":")
                self.__legend.setLineWidth(1.5)
        self.__legend.update()


class HookedStandardItem(qt.QStandardItem):
    def __init__(self, text: str):
        qt.QStandardItem.__init__(self, text)
        self.modelUpdated: Optional[Callable[[qt.QStandardItem], None]] = None

    def setData(self, value, role=qt.Qt.UserRole + 1):
        qt.QStandardItem.setData(self, value, role)
        if self.modelUpdated is not None:
            self.modelUpdated(self)


class RadioPropertyItemDelegate(qt.QStyledItemDelegate):
    def __init__(self, parent):
        qt.QStyledItemDelegate.__init__(self, parent=parent)

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(RadioPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = qt.QRadioButton(parent=parent)
        editor.setAutoExclusive(False)
        editor.clicked.connect(self.__editorsChanged)
        editor.setMinimumSize(editor.minimumSizeHint())
        editor.setMaximumSize(editor.minimumSizeHint())
        editor.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        return editor

    def __editorsChanged(self):
        editor = self.sender()
        self.commitData.emit(editor)

    def setEditorData(self, editor: qt.QWidget, index):
        data = index.data(role=RadioRole)
        old = editor.blockSignals(True)
        if data == qt.Qt.Checked:
            editor.setVisible(True)
            editor.setChecked(True)
        elif data == qt.Qt.Unchecked:
            editor.setVisible(True)
            editor.setChecked(False)
        elif data is None:
            editor.setVisible(False)
        else:
            _logger.warning("Unsupported data %s", data)
        editor.blockSignals(old)

    def setModelData(self, editor, model, index):
        data = qt.Qt.Checked if editor.isChecked() else qt.Qt.Unchecked
        model.setData(index, data, role=RadioRole)

    def updateEditorGeometry(self, editor, option, index):
        # Center the widget to the cell
        size = editor.sizeHint()
        half = size / 2
        halfPoint = qt.QPoint(half.width(), half.height() - 1)
        pos = option.rect.center() - halfPoint
        editor.move(pos)
