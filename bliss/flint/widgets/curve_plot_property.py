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

from silx.gui import qt
from silx.gui.plot import LegendSelector
from silx.gui import colors
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model
from bliss.flint.model import scan_model


PlotItemRole = qt.Qt.UserRole + 100


class YAxesEditor(qt.QWidget):

    valueChanged = qt.Signal()

    def __init__(self, parent=None):
        qt.QWidget.__init__(self, parent=parent)
        self.setContentsMargins(1, 1, 1, 1)
        self.__plotItem = None
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.__group = qt.QButtonGroup(self)

        y1Check = qt.QRadioButton(self)
        y1Check.setObjectName("y1")
        y2Check = qt.QRadioButton(self)
        y2Check.setObjectName("y2")

        self.__group.addButton(y1Check)
        self.__group.addButton(y2Check)
        self.__group.setExclusive(True)
        self.__group.buttonClicked[qt.QAbstractButton].connect(self.__checkedChanged)

        layout.addWidget(y1Check)
        layout.addWidget(y2Check)

    def __getY1Axis(self):
        return self.findChildren(qt.QRadioButton, "y1")[0]

    def __getY2Axis(self):
        return self.findChildren(qt.QRadioButton, "y2")[0]

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

        w = self.__getY1Axis()
        w.setEnabled(not isReadOnly)

        w = self.__getY2Axis()
        w.setEnabled(not isReadOnly)

        self.__updateToolTips()

    def __isReadOnly(self):
        # FIXME: It would be good to avoid magic hasattr
        return self.__plotItem is not None and not hasattr(self.__plotItem, "setYAxis")

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
        self.valueChanged.emit()

    def __plotItemChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.YAXIS:
            self.__plotItemYAxisChanged()

    def __plotItemYAxisChanged(self):
        try:
            axis = self.__plotItem.yAxis()
        except:
            # FIXME: Add debug in case
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
        plotItem = index.data(PlotItemRole)
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


class VisibilityPropertyItemDelegate(qt.QStyledItemDelegate):

    VisibilityRole = qt.Qt.UserRole + 1

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(VisibilityPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = qt.QCheckBox(parent=parent)
        editor.toggled.connect(self.__commitData)
        state = index.data(self.VisibilityRole)
        editor.setChecked(state == qt.Qt.Checked)

        # FIXME remove the hardcoded size, rework the icon and use size.height as a constraint
        size = editor.sizeHint() + qt.QSize(5, 5)
        iconChecked = icons.getQFile("flint:icons/visible")
        iconUnchecked = icons.getQFile("flint:icons/visible-disabled")

        style = f"""
QCheckBox::indicator {{
    width: {size.width()}px;
    height: {size.height()}px;
}}
QCheckBox::indicator:checked {{
    image: url({iconChecked.fileName()});
}}
QCheckBox::indicator:unchecked {{
    image: url({iconUnchecked.fileName()});
}}
"""
        editor.setStyleSheet(style)

        state = index.data(self.VisibilityRole)
        self.__updateEditorStyle(editor, state)
        return editor

    def __commitData(self):
        editor = self.sender()
        self.commitData.emit(editor)

    def __updateEditorStyle(self, editor: qt.QCheckBox, state: qt.Qt.CheckState):
        editor.setVisible(state is not None)

    def setEditorData(self, editor, index):
        state = index.data(self.VisibilityRole)
        self.__updateEditorStyle(editor, state)

    def setModelData(self, editor, model, index):
        state = qt.Qt.Checked if editor.isChecked() else qt.Qt.Unchecked
        model.setData(index, state, role=self.VisibilityRole)

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
            plot.removeItem(plotItem)

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
        # FIXME: It would be good to implement it in silx
        color = colors.rgba(color)
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
                self.setLineColor(color)
                self.setLineStyle(style.lineStyle)
                self.setLineWidth(1.5)
            except Exception as e:
                # FIXME: Log it better
                print(e)
                self.setLineColor("grey")
                self.setLineStyle(":")
                self.setLineWidth(1.5)
        self.update()


class _HookedStandardItem(qt.QStandardItem):
    def __init__(self, text: str):
        qt.QStandardItem.__init__(self, text)
        self.modelUpdated: Optional[Callable[[qt.QStandardItem], None]] = None

    def setData(self, value, role=qt.Qt.UserRole + 1):
        qt.QStandardItem.setData(self, value, role)
        if self.modelUpdated is not None:
            self.modelUpdated(self)


class _DataItem(qt.QStandardItem):
    def __init__(self, text: str = ""):
        qt.QStandardItem.__init__(self, text)
        self.__xaxis = qt.QStandardItem("")
        self.__yaxes = _HookedStandardItem("")
        self.__displayed = _HookedStandardItem("")
        self.__style = qt.QStandardItem("")
        self.__remove = qt.QStandardItem("")

        icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)
        self.__plotModel: Optional[plot_model.Plot] = None
        self.__plotItem: Optional[plot_model.Item] = None
        self.__channel: Optional[scan_model.Channel] = None

    def setPlotModel(self, plotModel: plot_model.Plot):
        self.__plotModel = plotModel

    def axesItem(self) -> qt.QStandardItem:
        return self.__yaxes

    def styleItem(self) -> qt.QStandardItem:
        return self.__style

    def items(self) -> List[qt.QStandardItem]:
        return [
            self,
            self.__xaxis,
            self.__yaxes,
            self.__displayed,
            self.__style,
            self.__remove,
        ]

    def __yAxisChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            # There is a plot item already
            return
        else:
            assert self.__channel is not None
            assert self.__plotModel is not None
            plot = self.__plotModel
            yAxis = item.data(role=YAxesPropertyItemDelegate.YAxesRole)
            assert yAxis in ["left", "right"]

            # Reach the master device
            topMaster = self.__channel.device().topMaster()
            scan = topMaster.scan()

            # Reach any plot item from this master
            for item in plot.items():
                if not isinstance(item, plot_curve_model.CurveItem):
                    continue
                channelName = item.xChannel().name()
                channel = scan.getChannelByName(channelName)
                assert channel is not None
                itemMaster = channel.device().topMaster()
                if itemMaster is topMaster:
                    break
            else:
                item = None

            if item is not None:
                newItem = plot_curve_model.CurveItem(plot)
                newItem.setXChannel(plot_model.ChannelRef(plot, channelName))
                newItem.setYChannel(plot_model.ChannelRef(plot, self.__channel.name()))
                plot.addItem(newItem)
            else:
                # No other x-axis is specified
                # Reach another channel name from the same top master
                channelNames = []
                for device in scan.devices():
                    if device.topMaster() is not topMaster:
                        continue
                    channelNames.extend([c.name() for c in device.channels()])
                channelNames.remove(self.__channel.name())

                if len(channelNames) > 0:
                    # Pick the first one
                    # FIXME: Maybe we could use scan infos to reach the default channel
                    channelName = channelNames[0]
                else:
                    # FIXME: Maybe it's better idea to display it with x-index
                    channelName = self.__channel.name()

                newItem = plot_curve_model.CurveItem(plot)
                newItem.setXChannel(plot_model.ChannelRef(plot, channelName))
                newItem.setYChannel(plot_model.ChannelRef(plot, self.__channel.name()))
                plot.addItem(newItem)

    def __visibilityViewChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            state = item.data(VisibilityPropertyItemDelegate.VisibilityRole)
            self.__plotItem.setVisible(state == qt.Qt.Checked)

    def setDevice(self, device: scan_model.Device):
        if device.isMaster():
            text = "Master %s" % device.name()
            icon = icons.getQIcon("flint:icons/item-timer")
        else:
            text = "Device %s" % device.name()
            icon = icons.getQIcon("flint:icons/item-device")
        self.setText(text)
        self.setIcon(icon)
        self.__xaxis.setCheckable(False)

    def setChannel(self, channel: scan_model.Channel, tree: qt.QTreeView):
        self.__channel = channel
        text = "Channel %s" % channel.name()
        self.setText(text)
        icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)

        self.__xaxis.setCheckable(True)
        self.__yaxes.modelUpdated = self.__yAxisChanged

        tree.openPersistentEditor(self.__yaxes.index())

    def setPlotItem(self, plotItem: plot_model.Item, tree: qt.QTreeView, flintModel):
        self.__plotItem = plotItem

        self.__yaxes.setData(plotItem, role=PlotItemRole)
        self.__style.setData(plotItem, role=PlotItemRole)
        self.__remove.setData(plotItem, role=PlotItemRole)

        self.__xaxis.setCheckable(True)
        self.__yaxes.modelUpdated = self.__yAxisChanged

        if plotItem is not None:
            isVisible = plotItem.isVisible()
            state = qt.Qt.Checked if isVisible else qt.Qt.Unchecked
            self.__displayed.setData(
                state, role=VisibilityPropertyItemDelegate.VisibilityRole
            )
            self.__displayed.modelUpdated = self.__visibilityViewChanged
        else:
            self.__displayed.setData(
                None, role=VisibilityPropertyItemDelegate.VisibilityRole
            )
            self.__displayed.modelUpdated = None

        if isinstance(plotItem, plot_curve_model.CurveItem):
            icon = icons.getQIcon("flint:icons/item-channel")
            self.setIcon(icon)
        elif isinstance(plotItem, plot_curve_model.CurveMixIn):
            icon = icons.getQIcon("flint:icons/item-func")
            self.setIcon(icon)
        elif isinstance(plotItem, plot_curve_model.CurveStatisticMixIn):
            icon = icons.getQIcon("flint:icons/item-stats")
            self.setIcon(icon)

        # FIXME: It have to be converted into delegate
        tree.openPersistentEditor(self.__yaxes.index())
        tree.openPersistentEditor(self.__displayed.index())
        tree.openPersistentEditor(self.__remove.index())
        widget = StylePropertyWidget(tree)
        widget.setPlotItem(self.__plotItem)
        widget.setFlintModel(flintModel)
        tree.setIndexWidget(self.__style.index(), widget)


class CurvePlotPropertyWidget(qt.QWidget):

    NameColumn = 0
    XAxisColumn = 1
    YAxesColumn = 2
    VisibleColumn = 3
    StyleColumn = 4
    RemoveColumn = 5

    def __init__(self, parent=None):
        super(CurvePlotPropertyWidget, self).__init__(parent=parent)
        self.__scan = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__plotModel: Union[None, plot_model.Plot] = None
        self.__tree = qt.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__yAxesDelegate = YAxesPropertyItemDelegate(self)
        self.__visibilityDelegate = VisibilityPropertyItemDelegate(self)
        self.__removeDelegate = RemovePropertyItemDelegate(self)

        model = qt.QStandardItemModel(self)

        self.__tree.setModel(model)
        self.__scan = None
        self.__focusWidget = None

        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.__tree)

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
            self.__setScan(None)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)
            self.__setScan(self.__flintModel.currentScan())

    def setFocusWidget(self, widget):
        if self.__focusWidget is not None:
            widget.plotModelUpdated.disconnect(self.__plotModelUpdated)
        self.__focusWidget = widget
        if self.__focusWidget is not None:
            widget.plotModelUpdated.connect(self.__plotModelUpdated)
        self.__plotModelUpdated(widget.plotModel())

    def __plotModelUpdated(self, plotModel):
        self.setPlotModel(plotModel)

    def setPlotModel(self, plotModel: plot_model.Plot):
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.disconnect(self.__structureChanged)
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.connect(self.__structureChanged)
        self.__updateTree()

    def __currentScanChanged(self):
        self.__setScan(self.__flintModel.currentScan())

    def __structureChanged(self):
        self.__updateTree()

    def plotModel(self) -> Union[None, plot_model.Plot]:
        return self.__plotModel

    def __setScan(self, scan):
        self.__scan = scan
        self.__updateTree()

    def __updateTree(self):
        # FIXME: expanded/collapsed items have to be restored

        model = self.__tree.model()
        model.clear()

        if self.__plotModel is None:
            foo = qt.QStandardItem("Empty")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(
            ["Name", "X", "Y1/Y2", "Displayed", "Style", "Remove", ""]
        )
        self.__tree.setItemDelegateForColumn(self.YAxesColumn, self.__yAxesDelegate)
        self.__tree.setItemDelegateForColumn(
            self.VisibleColumn, self.__visibilityDelegate
        )
        self.__tree.setItemDelegateForColumn(self.RemoveColumn, self.__removeDelegate)
        header = self.__tree.header()
        header.setSectionResizeMode(self.NameColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.XAxisColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.YAxesColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.VisibleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.StyleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.RemoveColumn, qt.QHeaderView.ResizeToContents)

        sourceTree: Dict[plot_model.Item, qt.QStandardItem] = {}
        scanTree = {}
        channelItems = {}

        scan = self.__scan

        if self.__scan is not None:
            for device in self.__scan.devices():
                item = _DataItem()
                scanTree[device] = item

                master = device.master()
                if master is None:
                    # Root device
                    parent = model
                else:
                    itemMaster = scanTree.get(master, None)
                    if itemMaster is None:
                        parent = model
                        print("Device list is not well ordered")
                    else:
                        parent = itemMaster
                parent.appendRow(item.items())
                # It have to be done when model index are initialized
                item.setDevice(device)

                for channel in device.channels():
                    channelItem = _DataItem()
                    item.appendRow(channelItem.items())
                    # It have to be done when model index are initialized
                    channelItem.setChannel(channel, self.__tree)
                    channelItem.setPlotModel(self.__plotModel)
                    channelItems[channel.name()] = channelItem

        itemWithoutLocation = qt.QStandardItem("Not linked to this scan")
        itemWithoutMaster = qt.QStandardItem("Not linked to a master")
        model.appendRow(itemWithoutLocation)
        model.appendRow(itemWithoutMaster)

        xChannelPerMasters = self.__getXChannelPerMasters(scan, self.__plotModel)

        for plotItem in self.__plotModel.items():
            parentChannel = None

            if isinstance(plotItem, plot_curve_model.ScanItem):
                continue

            if isinstance(plotItem, plot_model.AbstractComputableItem):
                source = plotItem.source()
                if source is None:
                    parent = itemWithoutLocation
                else:
                    itemSource = sourceTree.get(source, None)
                    if itemSource is None:
                        parent = itemWithoutMaster
                        print("Item list is not well ordered")
                    else:
                        parent = itemSource
            else:
                if scan is None:
                    parent = itemWithoutLocation
                else:
                    if isinstance(plotItem, plot_curve_model.CurveItem):
                        if not plotItem.isValid():
                            continue
                        topMaster = self.__fromSameTopMaster(scan, plotItem)
                        xChannelName = plotItem.xChannel().name()
                        if (
                            topMaster is not None
                            and xChannelPerMasters[topMaster] == xChannelName
                        ):
                            # The x-channel is what it is expected then we can link the y-channel
                            yChannelName = plotItem.yChannel().name()
                            parentChannel = channelItems[yChannelName]
                        else:
                            parent = itemWithoutLocation

            if parentChannel is not None:
                parentChannel.setPlotItem(plotItem, self.__tree, self.__flintModel)
                sourceTree[plotItem] = parentChannel
            else:
                itemClass = plotItem.__class__
                text = "%s" % itemClass.__name__
                item = _DataItem(text)
                parent.appendRow(item.items())
                # It have to be done when model index are initialized
                item.setPlotItem(plotItem, self.__tree, self.__flintModel)
                sourceTree[plotItem] = item

        self.__tree.expandAll()

    def __fromSameTopMaster(
        self, scan: scan_model.Scan, plotItem: plot_curve_model.CurveItem
    ) -> Union[None, scan_model.Device]:
        if not plotItem.isValid():
            return None
        x = plotItem.xChannel().name()
        y = plotItem.yChannel().name()
        channelX = scan.getChannelByName(x)
        if channelX is None:
            return None
        channelY = scan.getChannelByName(y)
        if channelY is None:
            return None
        topMasterX = channelX.device().topMaster()
        topMasterY = channelY.device().topMaster()
        if topMasterX is not topMasterY:
            return None
        return topMasterX

    def __getXChannelPerMasters(
        self, scan: scan_model.Scan, plotModel: plot_curve_model.CurvePlot
    ):
        if scan is None:
            return {}
        if plotModel is None:
            return {}

        # Count the amount of same x-channel per top masters
        xChannelsPerMaster: Dict[scan_model.Device, Dict[str, int]] = {}
        for plotItem in plotModel.items():
            if not isinstance(plotItem, plot_curve_model.CurveItem):
                continue
            # Here is only top level curve items
            xChannel = plotItem.xChannel()
            if xChannel is None:
                continue
            xChannelName = xChannel.name()
            channel = scan.getChannelByName(xChannelName)
            if channel is not None:
                topMaster = channel.device().topMaster()
                if topMaster not in xChannelsPerMaster:
                    counts: Dict[str, int] = {}
                    xChannelsPerMaster[topMaster] = counts
                else:
                    counts = xChannelsPerMaster[topMaster]

                counts[xChannelName] = counts.get(xChannelName, 0) + 1

        # Returns the most used channels
        xChannelPerMaster = {}
        for master, counts in xChannelsPerMaster.items():
            channels = sorted(counts.keys(), key=lambda x: counts[x])
            most_often_used_channel = channels[0]
            xChannelPerMaster[master] = most_often_used_channel
        return xChannelPerMaster
