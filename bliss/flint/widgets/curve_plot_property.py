# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union

from silx.gui import qt
from silx.gui.plot import LegendSelector
from silx.gui import colors

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model
from bliss.flint.model import scan_model


PlotItemData = qt.Qt.UserRole + 100


class AxesEditor(qt.QWidget):
    def __init__(self, parent=None):
        qt.QWidget.__init__(self, parent=parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.__plotItem = None
        layout = qt.QHBoxLayout(self)

        xCheck = qt.QCheckBox(self)
        xCheck.setObjectName("x")
        xCheck.setVisible(False)
        y1Check = qt.QCheckBox(self)
        y1Check.toggled.connect(self.__y1CheckChanged)
        y1Check.setObjectName("y1")
        y1Check.setVisible(False)
        y2Check = qt.QCheckBox(self)
        y2Check.setObjectName("y2")
        y2Check.toggled.connect(self.__y2CheckChanged)
        y2Check.setVisible(False)

        layout.addWidget(xCheck)
        layout.addWidget(y1Check)
        layout.addWidget(y2Check)

    def setPlotItem(self, plotItem):
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.disconnect(self.__plotItemChanged)
        self.__plotItem = plotItem
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.connect(self.__plotItemChanged)
            self.__plotItemYAxisChanged()

        isReadOnly = hasattr(self.__plotItem, "setYAxis")
        isVisible = self.__plotItem is not None

        w = self.findChildren(qt.QCheckBox, "x")[0]
        w.setVisible(isVisible)
        w.setEnabled(isReadOnly)
        w = self.findChildren(qt.QCheckBox, "y1")[0]
        w.setVisible(isVisible)
        w.setEnabled(isReadOnly)
        w = self.findChildren(qt.QCheckBox, "y2")[0]
        w.setVisible(isVisible)
        w.setEnabled(isReadOnly)

    def __y1CheckChanged(self):
        if self.__plotItem is None:
            return
        yAxis = self.findChildren(qt.QCheckBox, "y1")[0]
        isChecked = yAxis.isChecked()
        axis = "left" if isChecked else "right"
        self.__plotItem.setYAxis(axis)

    def __y2CheckChanged(self):
        if self.__plotItem is None:
            return
        yAxis = self.findChildren(qt.QCheckBox, "y2")[0]
        isChecked = yAxis.isChecked()
        axis = "left" if not isChecked else "right"
        self.__plotItem.setYAxis(axis)

    def __plotItemChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.YAXIS:
            self.__plotItemYAxisChanged()

    def __plotItemYAxisChanged(self):
        try:
            axis = self.__plotItem.yAxis()
        except:
            # FIXME: Add debug in case
            axis = None

        y1Axis = self.findChildren(qt.QCheckBox, "y1")[0]
        old = y1Axis.blockSignals(True)
        y1Axis.setChecked(axis == "left")
        y1Axis.blockSignals(old)

        y2Axis = self.findChildren(qt.QCheckBox, "y2")[0]
        old = y2Axis.blockSignals(True)
        y2Axis.setChecked(axis == "right")
        y2Axis.blockSignals(old)


class AxesPropertyItemDelegate(qt.QStyledItemDelegate):
    def __init__(self, parent):
        qt.QStyledItemDelegate.__init__(self, parent=parent)

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(AxesPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = AxesEditor(parent=parent)
        plotItem = self.getPlotItem(index)
        editor.setPlotItem(plotItem)

        editor.setMinimumSize(editor.sizeHint())
        editor.setMaximumSize(editor.sizeHint())
        editor.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        return editor

    def getPlotItem(self, index) -> plot_model.Item:
        plotItem = index.data(PlotItemData)
        if not isinstance(plotItem, plot_model.Item):
            return None
        return plotItem

    def setEditorData(self, editor, index):
        plotItem = self.getPlotItem(index)
        editor.setPlotItem(plotItem)

    def setModelData(self, editor, model, index):
        # Already up to date
        pass

    def updateEditorGeometry(self, editor: qt.QWidget, option, index):
        """
        Update the geometry of the editor according to the changes of the view.
        """
        # Set widget to the mid-left
        size = editor.sizeHint()
        half = size / 2
        halfPoint = qt.QPoint(0, half.height())
        halfDest = qt.QPoint(
            option.rect.left(), option.rect.top() + option.rect.height() // 2
        )
        pos = halfDest - halfPoint
        editor.move(pos)


class StylePropertyWidget(LegendSelector.LegendIcon):
    def __init__(self, parent):
        LegendSelector.LegendIcon.__init__(self, parent=parent)
        self.__plotItem = None
        self.__flintModel = None
        self.__scan = None

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

    def __setScan(self, scan: scan_model.Scan):
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


class CurvePlotPropertyWidget(qt.QWidget):
    def __init__(self, parent=None):
        super(CurvePlotPropertyWidget, self).__init__(parent=parent)
        self.__scan = None
        self.__flintModel = None
        self.__plotModel = None
        self.__tree = qt.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__axesDelegate = AxesPropertyItemDelegate(self)

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
        pass

    def plotModel(self) -> plot_model.Plot:
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

        model.setHorizontalHeaderLabels(["Name", "Axes", "Style", ""])
        self.__tree.setItemDelegateForColumn(1, self.__axesDelegate)
        header = self.__tree.header()
        header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, qt.QHeaderView.ResizeToContents)

        sourceTree = {}
        scanTree = {}
        channelItems = {}

        scan = self.__scan

        if self.__scan is not None:
            for device in self.__scan.devices():
                if device.isMaster():
                    item = qt.QStandardItem("Master %s" % device.name())
                else:
                    item = qt.QStandardItem("Device %s" % device.name())
                scanTree[device] = item
                for channel in device.channels():
                    channelItem = qt.QStandardItem("Channel %s" % channel.name())
                    axesItem = qt.QStandardItem("")
                    styleItem = qt.QStandardItem("")
                    item.appendRow([channelItem, axesItem, styleItem])
                    channelItems[channel.name()] = channelItem

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

                axesItem = qt.QStandardItem("")
                styleItem = qt.QStandardItem("")
                parent.appendRow([item, axesItem, styleItem])

        itemWithoutLocation = qt.QStandardItem("Not linked to this scan")
        model.appendRow(itemWithoutLocation)

        xChannelPerMasters = self.__getXChannelPerMasters(scan, self.__plotModel)

        for plotItem in self.__plotModel.items():
            itemClass = plotItem.__class__
            item = qt.QStandardItem("%s" % itemClass.__name__)
            sourceTree[plotItem] = item

            if isinstance(plotItem, plot_model.AbstractComputableItem):
                source = plotItem.source()
                if source is None:
                    parent = itemWithoutLocation
                else:
                    itemSource = sourceTree.get(source, None)
                    if itemSource is None:
                        parent = model
                        print("Item list is not well ordered")
                    else:
                        parent = itemSource
            else:
                if scan is None:
                    parent = itemWithoutLocation
                else:
                    if isinstance(plotItem, plot_curve_model.CurveItem):
                        topMaster = self.__fromSameTopMaster(scan, plotItem)
                        xChannelName = plotItem.xChannel().name()
                        if (
                            topMaster is not None
                            and xChannelPerMasters[topMaster] == xChannelName
                        ):
                            # The x-channel is what it is expected then we can link the y-channel
                            yChannelName = plotItem.yChannel().name()
                            parent = channelItems[yChannelName]
                        else:
                            parent = itemWithoutLocation

            axesItem = qt.QStandardItem("")
            styleItem = qt.QStandardItem("")
            createStyleWidget = False
            if isinstance(
                plotItem,
                (plot_curve_model.CurveMixIn, plot_curve_model.CurveStatisticMixIn),
            ):
                axesItem.setData(plotItem, role=PlotItemData)
                styleItem.setData(plotItem, role=PlotItemData)
                createStyleWidget = True
            parent.appendRow([item, axesItem, styleItem])
            self.__tree.openPersistentEditor(axesItem.index())
            if createStyleWidget:
                widget = StylePropertyWidget(self.__tree)
                widget.setPlotItem(plotItem)
                widget.setFlintModel(self.__flintModel)
                self.__tree.setIndexWidget(styleItem.index(), widget)

        self.__tree.expandAll()

    def __fromSameTopMaster(
        self, scan: scan_model.Scan, plotItem: plot_curve_model.CurveItem
    ) -> Union[None, scan_model.Device]:
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
        xChannelsPerMaster = {}
        for plotItem in self.__plotModel.items():
            if not isinstance(plotItem, plot_curve_model.CurveItem):
                continue
            # Here is only top level curve items
            xChannel = plotItem.xChannel()
            xChannelName = xChannel.name()
            channel = scan.getChannelByName(xChannelName)
            if channel is not None:
                topMaster = channel.device().topMaster()
                if topMaster not in xChannelsPerMaster:
                    counts = {}
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
