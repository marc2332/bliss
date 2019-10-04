# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
from typing import List
from typing import Dict
from typing import Callable
from typing import Optional

import logging
import numpy

from silx.gui import qt
from silx.gui.plot import LegendSelector
from silx.gui import colors as silx_colors
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import scan_model
from bliss.flint.widgets.eye_check_box import EyeCheckBox
from bliss.flint.helper import model_helper


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


class StylePropertyWidget(LegendSelector.LegendIcon):
    def __init__(self, parent):
        LegendSelector.LegendIcon.__init__(self, parent=parent)
        self.__plotItem: Union[None, plot_model.Plot] = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__scan: Union[None, scan_model.Scan] = None
        self.__colormapLut = None

    def paint(self, painter, rect, palette):
        if self.__colormapLut is not None:
            pixmap = self.getColormapPixmap(self.__colormapLut)
            pixmapRect = qt.QRect(0, 0, _COLORMAP_PIXMAP_SIZE, 1)
            widthMargin = 4
            if self.symbol is None:
                halfHeight = 4
            else:
                halfHeight = 2
            dest = qt.QRect(
                rect.left() + widthMargin,
                rect.center().y() - halfHeight + 1,
                rect.width() - widthMargin * 2,
                halfHeight * 2,
            )
            painter.drawPixmap(dest, pixmap, pixmapRect)
        super(StylePropertyWidget, self).paint(painter, rect, palette)

    def getColormapPixmap(self, name=None, colors=None):
        """Return an icon preview from a LUT name.

        This icons are cached into a global structure.

        :param str name: Name of the LUT
        :param numpy.ndarray colors: Colors identify the LUT
        :rtype: qt.QIcon
        """
        if name is not None:
            iconKey = name
        else:
            iconKey = tuple(colors)
        icon = _colormapPixmap.get(iconKey, None)
        if icon is None:
            icon = self.createColormapPixmap(name, colors)
            _colormapPixmap[iconKey] = icon
        return icon

    def createColormapPixmap(self, name=None, colors=None):
        """Create and return an icon preview from a LUT name.

        This icons are cached into a global structure.

        :param str name: Name of the LUT
        :param numpy.ndarray colors: Colors identify the LUT
        :rtype: qt.QIcon
        """
        colormap = silx_colors.Colormap(name)
        size = _COLORMAP_PIXMAP_SIZE
        if name is not None:
            lut = colormap.getNColors(size)
        else:
            lut = colors
            if len(lut) > size:
                # Down sample
                step = int(len(lut) / size)
                lut = lut[::step]
            elif len(lut) < size:
                # Over sample
                indexes = numpy.arange(size) / float(size) * (len(lut) - 1)
                indexes = indexes.astype("int")
                lut = lut[indexes]
        if lut is None or len(lut) == 0:
            return qt.QIcon()

        pixmap = qt.QPixmap(size, 1)
        painter = qt.QPainter(pixmap)
        for i in range(size):
            rgb = lut[i]
            r, g, b = rgb[0], rgb[1], rgb[2]
            painter.setPen(qt.QColor(r, g, b))
            painter.drawPoint(qt.QPoint(i, 0))
        painter.end()
        return pixmap

    def setPlotItem(self, plotItem: plot_model.Item):
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.disconnect(self.__plotItemChanged)
        self.__plotItem = plotItem
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.connect(self.__plotItemChanged)
            self.__plotItemStyleChanged()

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

    def __update(self):
        plotItem = self.__plotItem
        if plotItem is None:
            self.setLineColor("red")
            self.setLineStyle(":")
            self.setLineWidth(1.5)
        else:
            scan = self.__scan
            try:
                style = plotItem.getStyle(scan)
                color = self.getQColor(style.lineColor)
                if style.symbolStyle is not None:
                    self.setSymbol(style.symbolStyle)
                    if style.symbolColor is None:
                        self.setSymbolColor(qt.QColor(0xE0, 0xE0, 0xE0))
                    else:
                        self.setSymbolColor(style.symbolColor)
                self.__colormapLut = style.colormapLut
                self.setLineColor(color)
                self.setLineStyle(style.lineStyle)
                self.setLineWidth(1.5)
            except Exception:
                _logger.error("Error while reaching style", exc_info=True)
                self.setLineColor("grey")
                self.setLineStyle(":")
                self.setLineWidth(1.5)
        self.update()


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
