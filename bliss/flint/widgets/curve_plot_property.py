# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
from typing import List
from typing import Dict
from typing import Optional
from typing import NamedTuple

import logging
import functools
import weakref

from silx.gui import qt
from silx.gui import icons
from silx.gui import utils as qtutils

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.model import scan_model
from bliss.flint.helper import model_helper, scan_history, scan_info_helper
from bliss.flint.helper.style_helper import DefaultStyleStrategy
from bliss.flint.utils import qmodelutils
from bliss.flint.widgets.select_channel_dialog import SelectChannelDialog
from . import delegates
from . import data_views
from . import _property_tree_helper


_logger = logging.getLogger(__name__)


class YAxesEditor(qt.QWidget):

    valueChanged = qt.Signal()

    def __init__(self, parent=None):
        qt.QWidget.__init__(self, parent=parent)
        self.setContentsMargins(1, 1, 1, 1)
        self.__plotItem = None
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self.__group = qt.QButtonGroup(self)
        self.__group.buttonPressed.connect(self.__buttonPressed)

        y1Check = qt.QRadioButton(self)
        y1Check.setObjectName("y1")
        y2Check = qt.QRadioButton(self)
        y2Check.setObjectName("y2")

        self.__group.addButton(y1Check)
        self.__group.addButton(y2Check)
        self.__group.setExclusive(True)
        self.__group.buttonClicked[qt.QAbstractButton].connect(self.__checkedChanged)

        self.__removeButton = delegates.RemovePlotItemButton(self)

        placeHolder = qt.QWidget(self)
        phLayout = qt.QVBoxLayout(placeHolder)
        phLayout.setContentsMargins(0, 0, 0, 0)
        phLayout.addWidget(self.__removeButton)
        self.__removeButton.setFixedSize(y2Check.sizeHint())
        placeHolder.setFixedSize(y2Check.sizeHint())
        icon = icons.getQIcon("flint:icons/remove-item-small")
        self.__removeButton.setIcon(icon)

        layout.addWidget(y1Check)
        layout.addWidget(y2Check)
        layout.addWidget(placeHolder)

    def __getY1Axis(self):
        return self.findChildren(qt.QRadioButton, "y1")[0]

    def __getY2Axis(self):
        return self.findChildren(qt.QRadioButton, "y2")[0]

    def __buttonPressed(self, button):
        if button.isChecked():
            # Remove the item if the radio is already checked
            self.__removeButton.click()

    def yAxis(self) -> str:
        if self.__getY1Axis().isChecked():
            return "left"
        elif self.__getY2Axis().isChecked():
            return "right"
        return ""

    def setPlotItem(self, plotItem):
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.disconnect(self.__plotItemChanged)
        self.__plotItem = plotItem
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.connect(self.__plotItemChanged)
            self.__plotItemYAxisChanged()

        isReadOnly = self.__isReadOnly()

        self.__removeButton.setPlotItem(plotItem)
        self.__removeButton.setVisible(plotItem is not None and not isReadOnly)

        w = self.__getY1Axis()
        w.setEnabled(not isReadOnly)

        w = self.__getY2Axis()
        w.setEnabled(not isReadOnly)

        self.__updateToolTips()

    def __isReadOnly(self):
        if self.__plotItem is None:
            return False
        return not isinstance(self.__plotItem, plot_item_model.CurveMixIn)

    def __updateToolTips(self):
        isReadOnly = self.__isReadOnly()

        w = self.__getY1Axis()
        if w.isChecked():
            w.setToolTip("Displayed within the Y1 axis")
        elif isReadOnly:
            w.setToolTip("")
        else:
            w.setToolTip("Display it within the Y1 axis")

        w = self.__getY2Axis()
        if w.isChecked():
            w.setToolTip("Displayed within the Y2 axis")
        elif isReadOnly:
            w.setToolTip("")
        else:
            w.setToolTip("Display it within the Y2 axis")

    def __checkedChanged(self, button: qt.QRadioButton):
        yAxis1 = self.__getY1Axis()
        yAxis2 = self.__getY2Axis()
        if button is yAxis1:
            axis = "left"
        elif button is yAxis2:
            axis = "right"
        else:
            assert False
        if self.__plotItem is not None:
            self.__plotItem.setYAxis(axis)
            plotModel = self.__plotItem.plot()
            # FIXME: It would be better to make it part of the model
            plotModel.tagUserEditTime()
        self.valueChanged.emit()

    def __plotItemChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.YAXIS:
            self.__plotItemYAxisChanged()

    def __plotItemYAxisChanged(self):
        try:
            axis = self.__plotItem.yAxis()
        except Exception:
            _logger.error(
                "Error while reaching y-axis from %s", self.__plotItem, exc_info=True
            )
            axis = None

        y1Axis = self.__getY1Axis()
        old = y1Axis.blockSignals(True)
        y1Axis.setChecked(axis == "left")
        y1Axis.blockSignals(old)

        y2Axis = self.__getY2Axis()
        old = y2Axis.blockSignals(True)
        y2Axis.setChecked(axis == "right")
        y2Axis.blockSignals(old)

        self.__updateToolTips()


class YAxesPropertyItemDelegate(qt.QStyledItemDelegate):

    YAxesRole = qt.Qt.UserRole + 2

    def __init__(self, parent):
        qt.QStyledItemDelegate.__init__(self, parent=parent)

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(YAxesPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = YAxesEditor(parent=parent)
        plotItem = self.getPlotItem(index)
        editor.setPlotItem(plotItem)
        if plotItem is None:
            editor.valueChanged.connect(self.__editorsChanged)

        editor.setMinimumSize(editor.sizeHint())
        editor.setMaximumSize(editor.sizeHint())
        editor.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        return editor

    def __editorsChanged(self):
        editor = self.sender()
        self.commitData.emit(editor)

    def getPlotItem(self, index) -> Union[None, plot_model.Item]:
        plotItem = index.data(delegates.PlotItemRole)
        if not isinstance(plotItem, plot_model.Item):
            return None
        return plotItem

    def setEditorData(self, editor, index):
        plotItem = self.getPlotItem(index)
        editor.setPlotItem(plotItem)

    def setModelData(self, editor, model, index):
        plotItem = self.getPlotItem(index)
        if plotItem is None:
            yAxis = editor.yAxis()
            model.setData(index, yAxis, role=self.YAxesRole)
        else:
            # Already up-to-date
            # From signals from plot items
            pass

    def updateEditorGeometry(self, editor, option, index):
        # Center the widget to the cell
        size = editor.sizeHint()
        half = size / 2
        halfPoint = qt.QPoint(half.width(), half.height() - 1)
        pos = option.rect.center() - halfPoint
        editor.move(pos)


class _AddItemAction(qt.QWidgetAction):
    def __init__(self, parent: qt.QObject):
        assert isinstance(parent, CurvePlotPropertyWidget)
        super(_AddItemAction, self).__init__(parent)
        parent.plotItemSelected.connect(self.__selectionChanged)

        widget = qt.QToolButton(parent)
        icon = icons.getQIcon("flint:icons/add-item")
        widget.setIcon(icon)
        widget.setAutoRaise(True)
        widget.setToolTip("Create new items in the plot")
        widget.setPopupMode(qt.QToolButton.InstantPopup)
        widget.setEnabled(False)
        widget.setText("Create items")
        self.setDefaultWidget(widget)

        menu = qt.QMenu(parent)
        menu.aboutToShow.connect(self.__aboutToShow)
        widget.setMenu(menu)

    def __aboutToShow(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        item = self.parent().selectedPlotItem()
        if isinstance(item, plot_item_model.CurveMixIn):
            menu.addSection("Statistics")

            action = qt.QAction(self)
            action.setText("Max marker")
            icon = icons.getQIcon("flint:icons/item-stats")
            action.setIcon(icon)
            action.triggered.connect(
                functools.partial(self.__createChildItem, plot_state_model.MaxCurveItem)
            )
            menu.addAction(action)

            action = qt.QAction(self)
            action.setText("Min marker")
            icon = icons.getQIcon("flint:icons/item-stats")
            action.setIcon(icon)
            action.triggered.connect(
                functools.partial(self.__createChildItem, plot_state_model.MinCurveItem)
            )
            menu.addAction(action)

            menu.addSection("Functions")

            action = qt.QAction(self)
            action.setText("Derivative function")
            icon = icons.getQIcon("flint:icons/item-func")
            action.setIcon(icon)
            action.triggered.connect(
                functools.partial(
                    self.__createChildItem, plot_state_model.DerivativeItem
                )
            )
            menu.addAction(action)

            action = qt.QAction(self)
            action.setText("Negative function")
            icon = icons.getQIcon("flint:icons/item-func")
            action.setIcon(icon)
            action.triggered.connect(
                functools.partial(self.__createChildItem, plot_state_model.NegativeItem)
            )
            menu.addAction(action)

            action = qt.QAction(self)
            action.setText("Gaussian fit")
            icon = icons.getQIcon("flint:icons/item-func")
            action.setIcon(icon)
            action.triggered.connect(
                functools.partial(
                    self.__createChildItem, plot_state_model.GaussianFitItem
                )
            )
            menu.addAction(action)

            action = qt.QAction(self)
            action.setText("Normalized function")
            icon = icons.getQIcon("flint:icons/item-func")
            action.setIcon(icon)
            action.triggered.connect(self.__createNormalized)
            menu.addAction(action)
        else:
            action = qt.QAction(self)
            action.setText("No available items")
            action.setEnabled(False)
            menu.addAction(action)

    def __selectionChanged(self, current: plot_model.Item):
        self.defaultWidget().setEnabled(current is not None)

    def __createChildItem(self, itemClass):
        parentItem = self.parent().selectedPlotItem()
        if parentItem is not None:
            plotModel = parentItem.plot()
            newItem = itemClass(plotModel)
            newItem.setSource(parentItem)
            with plotModel.transaction():
                plotModel.addItem(newItem)
            # FIXME: It would be better to make it part of the model
            plotModel.tagUserEditTime()

    def __createNormalized(self):
        parentItem = self.parent().selectedPlotItem()
        if parentItem is not None:
            parentWidget = self.parent()
            scan = parentWidget.scan()
            dialog = SelectChannelDialog(parentWidget)
            dialog.setScan(scan)
            result = dialog.exec_()
            if not result:
                return
            monitorName = dialog.selectedChannelName()
            if monitorName is None:
                return
            plotModel = parentItem.plot()
            newItem = plot_state_model.NormalizedCurveItem(plotModel)
            channel = plot_model.ChannelRef(plotModel, monitorName)
            newItem.setMonitorChannel(channel)
            newItem.setSource(parentItem)
            with plotModel.transaction():
                plotModel.addItem(newItem)
            # FIXME: It would be better to make it part of the model
            plotModel.tagUserEditTime()


class _DataItem(_property_tree_helper.ScanRowItem):

    XAxisIndexRole = 1

    def __init__(self):
        super(_DataItem, self).__init__()
        qt.QStandardItem.__init__(self)
        self.__xaxis = delegates.HookedStandardItem("")
        self.__yaxes = delegates.HookedStandardItem("")
        self.__displayed = delegates.HookedStandardItem("")
        self.__style = qt.QStandardItem("")
        self.__remove = qt.QStandardItem("")
        self.__error = qt.QStandardItem("")
        self.__xAxisSelected = False
        self.__role = None
        self.__device = None

        self.__plotModel: Optional[plot_model.Plot] = None
        self.__plotItem: Optional[plot_model.Item] = None
        self.__channel: Optional[scan_model.Channel] = None
        self.__treeView: Optional[qt.QTreeView] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

        self.setOtherRowItems(
            self.__xaxis,
            self.__yaxes,
            self.__displayed,
            self.__style,
            self.__remove,
            self.__error,
        )

    def __hash__(self):
        return hash(id(self))

    def channel(self) -> Optional[scan_model.Channel]:
        return self.__channel

    def setEnvironment(
        self, treeView: qt.QTreeView, flintState: flint_model.FlintState
    ):
        self.__treeView = treeView
        self.__flintModel = flintState

    def setPlotModel(self, plotModel: plot_model.Plot):
        self.__plotModel = plotModel

    def plotModel(self) -> Optional[plot_model.Plot]:
        return self.__plotModel

    def axesItem(self) -> qt.QStandardItem:
        return self.__yaxes

    def styleItem(self) -> qt.QStandardItem:
        return self.__style

    def updateError(self):
        scan = self.__flintModel.currentScan()
        if scan is None or self.__plotItem is None:
            # No message to reach
            self.__error.setText(None)
            self.__error.setIcon(qt.QIcon())
            return
        result = self.__plotItem.getErrorMessage(scan)
        if result is None:
            # Ths item is valid
            self.__error.setText(None)
            self.__error.setIcon(qt.QIcon())
            return

        self.__error.setText(result)
        icon = icons.getQIcon("flint:icons/warning")
        self.__error.setIcon(icon)

    def __yAxisChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            # There is a plot item already
            return
        else:
            assert self.__channel is not None
            assert self.__plotModel is not None
            plotModel = self.__plotModel
            yAxis = item.data(role=YAxesPropertyItemDelegate.YAxesRole)
            assert yAxis in ["left", "right"]

            _curve, _wasUpdated = model_helper.createCurveItem(
                plotModel, self.__channel, yAxis, allowIndexed=True
            )
            # FIXME: It would be better to make it part of the model
            plotModel.tagUserEditTime()

    def __visibilityViewChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            state = item.data(delegates.VisibilityRole)
            self.__plotItem.setVisible(state == qt.Qt.Checked)
            plotModel = self.__plotItem.plot()
            # FIXME: It would be better to make it part of the model
            plotModel.tagUserEditTime()

    def setSelectedXAxis(self):
        if self.__xAxisSelected:
            return
        self.__xAxisSelected = True

        old = self.__xaxis.modelUpdated
        self.__xaxis.modelUpdated = None
        try:
            self.__xaxis.setData(qt.Qt.Checked, role=delegates.RadioRole)
        finally:
            self.__xaxis.modelUpdated = old
        # It have to be closed to be refreshed. Sounds like a bug.
        self.__treeView.closePersistentEditor(self.__xaxis.index())
        self.__treeView.openPersistentEditor(self.__xaxis.index())

    def __xAxisChanged(self, item: qt.QStandardItem):
        assert self.__plotModel is not None
        plotModel = self.__plotModel

        if self.__channel is not None:
            topMaster = self.__channel.device().topMaster()
            scan = topMaster.scan()
            xChannelName = self.__channel.name()
            model_helper.updateXAxis(
                plotModel, scan, topMaster, xChannelName=xChannelName
            )
        elif self.__role == self.XAxisIndexRole:
            topMaster = self.__device.topMaster()
            scan = topMaster.scan()
            model_helper.updateXAxis(plotModel, scan, topMaster, xIndex=True)
        else:
            assert False
        # FIXME: It would be better to make it part of the model
        plotModel.tagUserEditTime()

    def setDevice(self, device: scan_model.Device):
        self.setDeviceLookAndFeel(device)
        self.__updateXAxisStyle(True, None)

    def __rootRow(self) -> int:
        item = self
        while item is not None:
            parent = item.parent()
            if parent is None:
                break
            item = parent
        return item.row()

    def __updateXAxisStyle(self, setAxisValue: bool, radioValue=None):
        # FIXME: avoid hard coded style
        cellColors = [qt.QColor(0xE8, 0xE8, 0xE8), qt.QColor(0xF5, 0xF5, 0xF5)]
        old = self.__xaxis.modelUpdated
        self.__xaxis.modelUpdated = None
        if setAxisValue:
            self.__xaxis.setData(radioValue, role=delegates.RadioRole)
        i = self.__rootRow()
        self.__xaxis.setBackground(cellColors[i % 2])
        self.__xaxis.modelUpdated = old

    def setRole(self, role, device=None):
        self.__role = role
        if role == self.XAxisIndexRole:
            assert device is not None
            self.__device = device
            items = self.__plotModel.items()
            if len(items) > 0:
                item = items[0]
                checked = isinstance(item, plot_item_model.XIndexCurveItem)
            else:
                checked = True
            self.setText("index")
            qtchecked = qt.Qt.Checked if checked else qt.Qt.Unchecked
            self.__updateXAxisStyle(True, qtchecked)
            self.__xaxis.modelUpdated = weakref.WeakMethod(self.__xAxisChanged)
            self.__treeView.openPersistentEditor(self.__xaxis.index())
            icon = icons.getQIcon("flint:icons/item-index")
            self.setIcon(icon)
        else:
            assert False, f"Role '{role}' is unknown"

    def setChannel(self, channel: scan_model.Channel):
        assert self.__treeView is not None
        self.__channel = channel
        self.setChannelLookAndFeel(channel)
        self.__updateXAxisStyle(True, qt.Qt.Unchecked)
        self.__xaxis.modelUpdated = weakref.WeakMethod(self.__xAxisChanged)
        self.__yaxes.modelUpdated = weakref.WeakMethod(self.__yAxisChanged)

        self.__treeView.openPersistentEditor(self.__xaxis.index())
        self.__treeView.openPersistentEditor(self.__yaxes.index())

    def data(self, role=qt.Qt.DisplayRole):
        if role == qt.Qt.ToolTipRole:
            return self.toolTip()
        return _property_tree_helper.ScanRowItem.data(self, role)

    def toolTip(self):
        if self.__role == self.XAxisIndexRole:
            return "Use data index as x-axis"
        elif self.__channel is not None:
            data = self.__channel.data()
            if data is not None:
                array = data.array()
            else:
                array = None
            if array is None:
                shape = "No data"
            elif array is tuple():
                shape = "Scalar"
            else:
                shape = " ?? ".join([str(s) for s in array.shape])
            name = self.__channel.name()
            return f"""<html><ul>
            <li><b>Channel name:</b> {name}</li>
            <li><b>Data shape:</b> {shape}</li>
            </ul></html>"""

        return None

    def plotItem(self) -> Optional[plot_model.Item]:
        return self.__plotItem

    def setPlotItem(self, plotItem):
        self.__plotItem = plotItem

        self.__yaxes.setData(plotItem, role=delegates.PlotItemRole)
        self.__style.setData(plotItem, role=delegates.PlotItemRole)
        self.__remove.setData(plotItem, role=delegates.PlotItemRole)

        self.__yaxes.modelUpdated = weakref.WeakMethod(self.__yAxisChanged)

        if plotItem is not None:
            isVisible = plotItem.isVisible()
            state = qt.Qt.Checked if isVisible else qt.Qt.Unchecked
            self.__displayed.setData(state, role=delegates.VisibilityRole)
            self.__displayed.modelUpdated = weakref.WeakMethod(
                self.__visibilityViewChanged
            )
        else:
            self.__displayed.setData(None, role=delegates.VisibilityRole)
            self.__displayed.modelUpdated = None

        if self.__channel is None:
            self.setPlotItemLookAndFeel(plotItem)

        if isinstance(plotItem, plot_item_model.CurveItem):
            self.__xaxis.modelUpdated = weakref.WeakMethod(self.__xAxisChanged)
            useXAxis = True
        elif isinstance(plotItem, plot_item_model.CurveMixIn):
            # self.__updateXAxisStyle(False, None)
            useXAxis = False
            self.__updateXAxisStyle(False)
        elif isinstance(plotItem, plot_state_model.CurveStatisticItem):
            useXAxis = False
            self.__updateXAxisStyle(False)

        # FIXME: It have to be converted into delegate
        if useXAxis:
            self.__treeView.openPersistentEditor(self.__xaxis.index())
        # FIXME: close/open is needed, sometime the item is not updated
        self.__treeView.closePersistentEditor(self.__yaxes.index())
        self.__treeView.openPersistentEditor(self.__yaxes.index())
        self.__treeView.openPersistentEditor(self.__displayed.index())
        self.__treeView.openPersistentEditor(self.__remove.index())
        widget = delegates.StylePropertyWidget(self.__treeView)
        widget.setPlotItem(self.__plotItem)
        widget.setFlintModel(self.__flintModel)
        self.__treeView.setIndexWidget(self.__style.index(), widget)

        self.updateError()


class ScanItem(NamedTuple):
    scan: scan_model.Scan
    plotModel: plot_model.Plot
    plotItem: plot_model.Item
    curveWidget: qt.QWidget


class ScanTableView(data_views.VDataTableView):
    ScanNbColumn = 0
    ScanTitleColumn = 1
    ScanStartTimeColumn = 2
    ScanStyleColumn = 3
    ScanRemoveColumn = 4

    scanSelected = qt.Signal(object)

    def __init__(self, parent=None):
        data_views.VDataTableView.__init__(self, parent=parent)
        self.setColumn(
            self.ScanNbColumn,
            title="Nb",
            delegate=delegates.ScanNumberDelegate,
            resizeMode=qt.QHeaderView.ResizeToContents,
        )
        self.setColumn(
            self.ScanTitleColumn,
            title="Title",
            delegate=delegates.ScanTitleDelegate,
            resizeMode=qt.QHeaderView.Stretch,
        )
        self.setColumn(
            self.ScanStartTimeColumn,
            title="Time",
            delegate=delegates.ScanStartTimeDelegate,
            resizeMode=qt.QHeaderView.ResizeToContents,
        )
        self.setColumn(
            self.ScanStyleColumn,
            title="Style",
            delegate=delegates.ScanStyleDelegate,
            resizeMode=qt.QHeaderView.ResizeToContents,
        )
        self.setColumn(
            self.ScanRemoveColumn,
            title="Remove",
            delegate=delegates.RemoveScanDelegate,
            resizeMode=qt.QHeaderView.ResizeToContents,
        )

        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        selectionModel = self.selectionModel()
        selectionModel.currentChanged.connect(self.__selectionChanged)
        vheader = self.verticalHeader()
        vheader.setDefaultSectionSize(30)
        vheader.sectionResizeMode(qt.QHeaderView.Fixed)

    def __selectionChanged(self, current: qt.QModelIndex, previous: qt.QModelIndex):
        model = self.model()
        index = model.index(current.row(), 0)
        scan = model.object(index)
        self.scanSelected.emit(scan.scan)

    def scanIndex(self, scan: scan_model.Scan) -> qt.QModelIndex:
        """Returns the index of the scan"""
        model = self.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            obj = model.object(index)
            if obj.scan is scan:
                return index
        return qt.QModelIndex()

    def selectScan(self, select: scan_model.Scan):
        index = self.scanIndex(select)
        selectionModel = self.selectionModel()
        # selectionModel.reset()
        mode = (
            qt.QItemSelectionModel.Clear
            | qt.QItemSelectionModel.Rows
            | qt.QItemSelectionModel.Current
            | qt.QItemSelectionModel.Select
        )
        selectionModel.select(index, mode)


class CurvePlotPropertyWidget(qt.QWidget):

    NameColumn = 0
    XAxisColumn = 1
    YAxesColumn = 2
    VisibleColumn = 3
    StyleColumn = 4
    RemoveColumn = 5

    plotItemSelected = qt.Signal(object)

    def __init__(self, parent=None):
        super(CurvePlotPropertyWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__plotModel: Union[None, plot_model.Plot] = None
        self.__tree = qt.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__structureInvalidated: bool = False
        self.__xAxisInvalidated: bool = False
        self.__xAxisDelegate = delegates.RadioPropertyItemDelegate(self)
        self.__yAxesDelegate = YAxesPropertyItemDelegate(self)
        self.__visibilityDelegate = delegates.VisibilityPropertyItemDelegate(self)
        self.__removeDelegate = delegates.RemovePropertyItemDelegate(self)

        model = qt.QStandardItemModel(self)
        self.__tree.setModel(model)
        selectionModel = self.__tree.selectionModel()
        selectionModel.currentChanged.connect(self.__selectionChanged)

        self.__scan = None
        self.__focusWidget = None

        toolBar = self.__createToolBar()

        self.setAutoFillBackground(True)
        self.__tree.setFrameShape(qt.QFrame.NoFrame)
        line = qt.QFrame(self)
        line.setFrameShape(qt.QFrame.HLine)
        line.setFrameShadow(qt.QFrame.Sunken)

        self.__scanListView = ScanTableView(self)
        self.__scanListModel = data_views.ObjectListModel(self)
        self.__scanListView.setSourceModel(self.__scanListModel)
        self.__scanListView.scanSelected.connect(self.__scanSelectionChanged)

        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolBar)
        layout.addWidget(line)
        layout.addWidget(self.__tree)
        layout.addWidget(self.__scanListView)

    def resizeEvent(self, event: qt.QResizeEvent):
        self.__updateScanViewHeight(event.size())
        return super(CurvePlotPropertyWidget, self).resizeEvent(event)

    def __removeAllItems(self):
        if self.__plotModel is None:
            return
        plotModel = self.__plotModel
        with plotModel.transaction():
            items = list(plotModel.items())
            for item in items:
                try:
                    plotModel.removeItem(item)
                except IndexError:
                    # Item was maybe already removed
                    pass
        # FIXME: It would be better to make it part of the model
        plotModel.tagUserEditTime()

    def __createToolBar(self):
        toolBar = qt.QToolBar(self)
        toolBar.setMovable(False)
        action = _AddItemAction(self)
        toolBar.addAction(action)

        toolBar.addSeparator()

        action = qt.QAction(self)
        icon = icons.getQIcon("flint:icons/reset-to-plotselect")
        action.setIcon(icon)
        action.setText("Reset with plotselect")
        action.setToolTip("Reset the plot to the original plotselect used")
        action.triggered.connect(self.__resetPlotWithOriginalPlot)
        toolBar.addAction(action)

        action = qt.QAction(self)
        icon = icons.getQIcon("flint:icons/remove-all-items")
        action.setIcon(icon)
        action.setToolTip("Remove all the items from the plot")
        action.triggered.connect(self.__removeAllItems)
        toolBar.addAction(action)

        toolBar.addSeparator()

        action = qt.QAction(self)
        icon = icons.getQIcon("flint:icons/scan-many")
        action.setCheckable(True)
        action.setIcon(icon)
        action.setToolTip("Enable displaying many scans and show the list")
        action.toggled.connect(self.__toggeledShowScans)
        toolBar.addAction(action)
        self.__storeScanAction = action

        action = qt.QWidgetAction(self)
        self.__nbStoredScans = qt.QSpinBox(self)
        self.__nbStoredScans.setRange(1, 20)
        self.__nbStoredScans.setToolTip("Max number of displayed scans")
        self.__nbStoredScans.valueChanged.connect(self.__nbStoredScansChanged)
        action.setDefaultWidget(self.__nbStoredScans)
        toolBar.addAction(action)
        self.__storeScanNumberAction = action

        action = qt.QAction(self)
        icon = icons.getQIcon("flint:icons/scan-history")
        action.setIcon(icon)
        action.setToolTip(
            "Load a previous scan stored in Redis (about 24 hour of history)"
        )
        action.triggered.connect(self.__requestLoadScanFromHistory)
        toolBar.addAction(action)

        return toolBar

    def __toggeledShowScans(self, checked):
        self.__scanListView.setVisible(checked)
        curveWidget = self.__focusWidget
        if curveWidget is not None:
            curveWidget.setPreviousScanStored(checked)
            self.__storeScanNumberAction.setVisible(checked)

    def __nbStoredScansChanged(self):
        value = self.__nbStoredScans.value()
        curveWidget = self.__focusWidget
        if curveWidget is not None:
            if value != curveWidget.maxStoredScans():
                curveWidget.setMaxStoredScans(value)
        self.__updateScanViewHeight(self.size())

    def __updateScanViewHeight(self, widgetSize: qt.QSize):
        maxHeight = widgetSize.height() // 2
        curveWidget = self.__focusWidget
        expectedRows = curveWidget.maxStoredScans()

        expectedHeight = 0
        vheader = self.__scanListView.verticalHeader()
        expectedHeight += expectedRows * vheader.defaultSectionSize()
        hscrollbar = self.__scanListView.horizontalScrollBar()
        if not hscrollbar.isHidden():
            expectedHeight += hscrollbar.height()
        hheader = self.__scanListView.horizontalHeader()
        if not hheader.isHidden():
            expectedHeight += hheader.height()

        expectedHeight = min(maxHeight, expectedHeight)
        self.__scanListView.setMinimumHeight(expectedHeight)
        self.__scanListView.setMaximumHeight(expectedHeight)

    def __resetPlotWithOriginalPlot(self):
        widget = self.__focusWidget
        scan = widget.scan()
        plots = scan_info_helper.create_plot_model(scan.scanInfo(), scan)
        plots = [p for p in plots if isinstance(p, plot_item_model.CurvePlot)]
        if len(plots) == 0:
            _logger.warning("No curve plot to display")
            qt.QMessageBox.warning(
                None, "Warning", "There was no curve plot in this scan"
            )
            return
        plotModel = plots[0]
        previousPlotModel = self.__plotModel

        # Reuse only available values
        if isinstance(previousPlotModel, plot_item_model.CurvePlot):
            model_helper.removeNotAvailableChannels(previousPlotModel, plotModel, scan)
            model_helper.copyItemsFromChannelNames(
                previousPlotModel, plotModel, scan=None
            )
        if plotModel.styleStrategy() is None:
            plotModel.setStyleStrategy(DefaultStyleStrategy(self.__flintModel))
        widget.setPlotModel(plotModel)

    def __requestLoadScanFromHistory(self):
        from bliss.flint.widgets.scan_history_dialog import ScanHistoryDialog

        sessionName = self.__flintModel.blissSessionName()

        dialog = ScanHistoryDialog(self)
        dialog.setSessionName(sessionName)
        result = dialog.exec_()
        if result:
            selection = dialog.selectedScanNodeNames()
            widget = self.__focusWidget
            if widget is None:
                _logger.error("No curve widget connected")
                return

            if len(selection) == 0:
                _logger.error("No selection")
                return

            nodeName = selection[0]
            try:
                self.__loadScanFromHistory(nodeName)
            except Exception:
                _logger.error("Error while loading scan from history", exc_info=True)
                qt.QMessageBox.critical(
                    None,
                    "Error",
                    "An error occurred while a scan was loading from the history",
                )

    def __loadScanFromHistory(self, nodeName: str):
        scan = scan_history.create_scan(nodeName)
        widget = self.__focusWidget
        if widget is not None:
            if widget.isPreviousScanStored():
                widget.insertScan(scan)
            else:
                plots = scan_info_helper.create_plot_model(scan.scanInfo(), scan)
                plots = [p for p in plots if isinstance(p, plot_item_model.CurvePlot)]
                if len(plots) == 0:
                    _logger.warning("No curve plot to display")
                    qt.QMessageBox.warning(
                        None, "Warning", "There was no curve plot in the selected scan"
                    )
                    return
                plotModel = plots[0]
                previousWidgetPlot = self.__plotModel

                # Reuse only available values
                if isinstance(previousWidgetPlot, plot_item_model.CurvePlot):
                    model_helper.removeNotAvailableChannels(
                        previousWidgetPlot, plotModel, scan
                    )
                    widget.setScan(scan)
                if previousWidgetPlot is None or previousWidgetPlot.isEmpty():
                    if plotModel.styleStrategy() is None:
                        plotModel.setStyleStrategy(
                            DefaultStyleStrategy(self.__flintModel)
                        )
                    widget.setPlotModel(plotModel)

    def __findItemFromPlotItem(
        self, requestedItem: plot_model.Item
    ) -> Optional[_DataItem]:
        """Returns a silx plot item from a flint plot item."""
        if requestedItem is None:
            return None
        model = self.__tree.model()
        for index in qmodelutils.iterAllItems(model):
            item = model.itemFromIndex(index)
            if isinstance(item, _DataItem):
                plotItem = item.plotItem()
                if plotItem is requestedItem:
                    return item
        return None

    def __selectionChangedFromPlot(self, current: plot_model.Item):
        self.selectPlotItem(current)

    def __scanSelectionChangedFromPlot(self, current: scan_model.Scan):
        self.__scanListView.selectScan(current)

    def selectPlotItem(self, select: plot_model.Item):
        selectionModel = self.__tree.selectionModel()
        if select is None:
            # Break reentrant signals
            selectionModel.setCurrentIndex(
                qt.QModelIndex(), qt.QItemSelectionModel.Clear
            )
            return
        if select is self.selectedPlotItem():
            # Break reentrant signals
            return
        item = self.__findItemFromPlotItem(select)
        flags = qt.QItemSelectionModel.Rows | qt.QItemSelectionModel.ClearAndSelect
        if item is None:
            index = qt.QModelIndex()
        else:
            index = item.index()
        selectionModel = self.__tree.selectionModel()
        selectionModel.setCurrentIndex(index, flags)
        self.__syncScanModel()

    def __scanSelectionChanged(self, scan: scan_model.Scan):
        curveWidget = self.__focusWidget
        if curveWidget is not None:
            curveWidget.selectScan(scan)

    def __selectionChanged(self, current: qt.QModelIndex, previous: qt.QModelIndex):
        model = self.__tree.model()
        index = model.index(current.row(), 0, current.parent())
        item = model.itemFromIndex(index)
        if isinstance(item, _DataItem):
            plotItem = item.plotItem()
        else:
            plotItem = None
        self.plotItemSelected.emit(plotItem)
        curveWidget = self.__focusWidget
        if curveWidget is not None:
            curveWidget.selectPlotItem(plotItem)

    def selectedPlotItem(self) -> Optional[plot_model.Item]:
        """Returns the current selected plot item, if one"""
        selectionModel = self.__tree.selectionModel()
        indices = selectionModel.selectedRows()
        index = indices[0] if len(indices) > 0 else qt.QModelIndex()
        if not index.isValid():
            return None
        model = self.__tree.model()
        index = model.index(index.row(), 0, index.parent())
        item = model.itemFromIndex(index)
        if isinstance(item, _DataItem):
            plotItem = item.plotItem()
            return plotItem
        return None

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        self.__flintModel = flintModel

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):
        if self.__focusWidget is not None:
            widget.plotModelUpdated.disconnect(self.__plotModelUpdated)
            widget.plotItemSelected.disconnect(self.__selectionChangedFromPlot)
            widget.scanSelected.disconnect(self.__scanSelectionChangedFromPlot)
            widget.scanModelUpdated.disconnect(self.__currentScanChanged)
            widget.scanListUpdated.disconnect(self.__currentScanListChanged)
        self.__focusWidget = widget
        if self.__focusWidget is not None:
            widget.plotModelUpdated.connect(self.__plotModelUpdated)
            widget.plotItemSelected.connect(self.__selectionChangedFromPlot)
            widget.scanSelected.connect(self.__scanSelectionChangedFromPlot)
            widget.scanModelUpdated.connect(self.__currentScanChanged)
            widget.scanListUpdated.connect(self.__currentScanListChanged)
            plotModel = widget.plotModel()
            scanModel = widget.scan()
        else:
            plotModel = None
            scanModel = None

        if widget is not None:
            scansVisible = widget.isPreviousScanStored()
            self.__scanListView.setVisible(scansVisible)
            self.__storeScanAction.setChecked(scansVisible)
            self.__nbStoredScans.setValue(widget.maxStoredScans())
            self.__storeScanNumberAction.setVisible(scansVisible)

        self.__currentScanChanged(scanModel)
        self.__currentScanListChanged(widget.scanList())
        self.__plotModelUpdated(plotModel)
        self.__syncScanModel()

    def __plotModelUpdated(self, plotModel):
        self.setPlotModel(plotModel)
        self.__syncScanModel()

    def setPlotModel(self, plotModel: plot_model.Plot):
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.disconnect(self.__structureChanged)
            self.__plotModel.itemValueChanged.disconnect(self.__itemValueChanged)
            self.__plotModel.transactionFinished.disconnect(self.__transactionFinished)
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.connect(self.__structureChanged)
            self.__plotModel.itemValueChanged.connect(self.__itemValueChanged)
            self.__plotModel.transactionFinished.connect(self.__transactionFinished)
        self.__updateTree()

    def __currentScanChanged(self, scanModel):
        self.__setScan(scanModel)

    def __currentScanListChanged(self, scanList):
        self.__syncScanModel()

    def __syncScanModel(self):
        widget = self.__focusWidget
        if widget is None:
            return
        plotModel = self.__plotModel
        if plotModel is None:
            return
        plotItem = widget.selectedPlotItem()
        scans = widget.scanList()
        scanList = [ScanItem(s, plotModel, plotItem, widget) for s in scans]
        self.__scanListModel.setObjectList(scanList)
        with qtutils.blockSignals(self.__scanListView):
            self.__scanListView.selectScan(widget.selectedScan())

    def __structureChanged(self):
        if self.__plotModel.isInTransaction():
            self.__structureInvalidated = True
        else:
            self.__updateTree()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        assert self.__plotModel is not None
        if eventType == plot_model.ChangeEventType.X_CHANNEL:
            if self.__plotModel.isInTransaction():
                self.__xAxisInvalidated = True
            else:
                self.__updateTree()
        elif eventType == plot_model.ChangeEventType.Y_CHANNEL:
            if self.__plotModel.isInTransaction():
                self.__xAxisInvalidated = True
            else:
                self.__updateTree()

    def __transactionFinished(self):
        updateTree = self.__xAxisInvalidated or self.__structureInvalidated
        if updateTree:
            self.__xAxisInvalidated = False
            self.__structureInvalidated = False
            self.__updateTree()

    def plotModel(self) -> Union[None, plot_model.Plot]:
        return self.__plotModel

    def __setScan(self, scan: Optional[scan_model.Scan]):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].disconnect(self.__scanDataUpdated)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].connect(self.__scanDataUpdated)
        self.__updateTree()

    def scan(self) -> Optional[scan_model.Scan]:
        return self.__scan

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        model = self.__tree.model()
        flags = qt.Qt.MatchWildcard | qt.Qt.MatchRecursive
        items = model.findItems("*", flags)
        channels = set(event.iterUpdatedChannels())
        # FIXME: This loop could be optimized
        for item in items:
            if isinstance(item, _DataItem):
                if item.channel() in channels:
                    item.updateError()

    def __genScanTree(
        self,
        model: qt.QStandardItemModel,
        scan: scan_model.Scan,
        channelFilter: scan_model.ChannelType,
    ) -> Dict[str, _DataItem]:
        """Feed the provided model with a tree of scan concepts (devices,
        channels).

        Returns a map from channel name to Qt items (`_DataItem`)
        """
        assert self.__tree is not None
        assert self.__flintModel is not None
        assert self.__plotModel is not None
        scanTree = {}
        channelItems: Dict[str, _DataItem] = {}

        devices: List[qt.QStandardItem] = []
        channelsPerDevices: Dict[qt.QStandardItem, int] = {}

        for device in scan.devices():
            item = _DataItem()
            item.setEnvironment(self.__tree, self.__flintModel)
            scanTree[device] = item

            master = device.master()
            if master is None:
                # Root device
                parent = model
            else:
                itemMaster = scanTree.get(master, None)
                if itemMaster is None:
                    parent = model
                    _logger.warning("Device list is not well ordered")
                else:
                    parent = itemMaster

            parent.appendRow(item.rowItems())
            # It have to be done when model index are initialized
            item.setDevice(device)
            devices.append(item)

            channels = []
            for channel in device.channels():
                if channel.type() != channelFilter:
                    continue
                channels.append(channel)

            if device.master() is None:
                indexItem = _DataItem()
                indexItem.setEnvironment(self.__tree, self.__flintModel)
                indexItem.setPlotModel(self.__plotModel)
                item.appendRow(indexItem.rowItems())
                # It have to be done when model index are initialized
                indexItem.setRole(_DataItem.XAxisIndexRole, device=device)

            for channel in channels:
                channelItem = _DataItem()
                channelItem.setEnvironment(self.__tree, self.__flintModel)
                item.appendRow(channelItem.rowItems())
                # It have to be done when model index are initialized
                channelItem.setChannel(channel)
                channelItem.setPlotModel(self.__plotModel)
                channelItems[channel.name()] = channelItem

            # Update channel use
            parent = item
            channelsPerDevices[parent] = 0
            while parent is not None:
                if parent in channelsPerDevices:
                    channelsPerDevices[parent] += len(channels)
                parent = parent.parent()
                if parent is None:
                    break

        # Clean up unused devices
        for device in reversed(devices):
            if device not in channelsPerDevices:
                continue
            if channelsPerDevices[device] > 0:
                continue
            parent = device.parent()
            if parent is None:
                parent = model
            parent.removeRows(device.row(), 1)

        return channelItems

    def __updateTree(self):
        collapsed = _property_tree_helper.getPathFromCollapsedNodes(self.__tree)
        selectedItem = self.selectedPlotItem()
        scrollx = self.__tree.horizontalScrollBar().value()
        scrolly = self.__tree.verticalScrollBar().value()

        model = self.__tree.model()
        model.clear()
        if self.__plotModel is None:
            return
        if self.__scan is None:
            return

        if self.__plotModel is None:
            model.setHorizontalHeaderLabels([""])
            foo = qt.QStandardItem("")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(
            ["Name", "X", "Y1/Y2", "Displayed", "Style", "Remove", "Message"]
        )
        self.__tree.setItemDelegateForColumn(self.XAxisColumn, self.__xAxisDelegate)
        self.__tree.setItemDelegateForColumn(self.YAxesColumn, self.__yAxesDelegate)
        self.__tree.setItemDelegateForColumn(
            self.VisibleColumn, self.__visibilityDelegate
        )
        self.__tree.setItemDelegateForColumn(self.RemoveColumn, self.__removeDelegate)
        self.__tree.setStyleSheet("QTreeView:item {padding: 0px 8px;}")
        header = self.__tree.header()
        header.setStyleSheet("QHeaderView { qproperty-defaultAlignment: AlignCenter; }")
        header.setSectionResizeMode(self.NameColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.XAxisColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.YAxesColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.VisibleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.StyleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.RemoveColumn, qt.QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(10)
        header.moveSection(self.StyleColumn, self.VisibleColumn)

        sourceTree: Dict[plot_model.Item, qt.QStandardItem] = {}
        scan = self.__scan
        if scan is not None:
            channelItems = self.__genScanTree(
                model, scan, scan_model.ChannelType.COUNTER
            )
        else:
            channelItems = {}

        itemWithoutLocation = qt.QStandardItem("Not linked to this scan")
        itemWithoutMaster = qt.QStandardItem("Not linked to a master")
        model.appendRow(itemWithoutLocation)
        model.appendRow(itemWithoutMaster)

        xChannelPerMasters = model_helper.getMostUsedXChannelPerMasters(
            scan, self.__plotModel
        )

        for plotItem in self.__plotModel.items():
            parentChannel = None

            if isinstance(plotItem, plot_item_model.ScanItem):
                continue
            if isinstance(plotItem, plot_item_model.AxisPositionMarker):
                continue

            if isinstance(plotItem, (plot_model.ComputableMixIn, plot_model.ChildItem)):
                source = plotItem.source()
                if source is None:
                    parent = itemWithoutLocation
                else:
                    itemSource = sourceTree.get(source, None)
                    if itemSource is None:
                        parent = itemWithoutMaster
                        _logger.warning("Item list is not well ordered")
                    else:
                        parent = itemSource
            else:
                if scan is None:
                    parent = itemWithoutLocation
                else:
                    if isinstance(plotItem, plot_item_model.CurveItem):
                        xChannel = plotItem.xChannel()
                        if xChannel is None:
                            yChannel = plotItem.yChannel()
                            if yChannel is not None:
                                yChannelName = yChannel.name()
                                parentChannel = channelItems.get(yChannelName, None)
                                if parentChannel is None:
                                    parent = itemWithoutLocation
                            else:
                                # item with bad content
                                continue
                        else:
                            topMaster = model_helper.getConsistentTopMaster(
                                scan, plotItem
                            )
                            xChannelName = xChannel.name()
                            if (
                                topMaster is not None
                                and xChannelPerMasters[topMaster] == xChannelName
                            ):
                                # The x-channel is what it is expected then we can link the y-channel
                                yChannel = plotItem.yChannel()
                                if yChannel is not None:
                                    yChannelName = yChannel.name()
                                    parentChannel = channelItems.get(yChannelName, None)
                                    if parentChannel is None:
                                        parent = itemWithoutLocation
                                xAxisItem = channelItems[xChannelName]
                                xAxisItem.setSelectedXAxis()
                                if yChannel is None:
                                    # This item must not be displayed
                                    continue
                            else:
                                parent = itemWithoutLocation

            if parentChannel is not None:
                parentChannel.setPlotItem(plotItem)
                sourceTree[plotItem] = parentChannel
            else:
                item = _DataItem()
                item.setEnvironment(self.__tree, self.__flintModel)
                parent.appendRow(item.rowItems())
                # It have to be done when model index are initialized
                item.setPlotItem(plotItem)
                sourceTree[plotItem] = item

        if itemWithoutLocation.rowCount() == 0:
            model.removeRows(itemWithoutLocation.row(), 1)
        if itemWithoutMaster.rowCount() == 0:
            model.removeRows(itemWithoutMaster.row(), 1)

        self.__tree.expandAll()
        _property_tree_helper.collapseNodesFromPaths(self.__tree, collapsed)
        self.__tree.horizontalScrollBar().setValue(scrollx)
        self.__tree.verticalScrollBar().setValue(scrolly)

        with qtutils.blockSignals(self):
            self.selectPlotItem(selectedItem)
