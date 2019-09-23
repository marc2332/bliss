# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from silx.gui import qt

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model


PlotItemData = qt.Qt.UserRole + 100


class AxesPropertyItemDelegate(qt.QStyledItemDelegate):
    def __init__(self, parent):
        qt.QStyledItemDelegate.__init__(self, parent=parent)

    class Editor(qt.QWidget):
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

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(AxesPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = self.Editor(parent=parent)
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
        model = self.__tree.model()
        model.clear()

        if self.__plotModel is None:
            foo = qt.QStandardItem("Empty")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(["Name", "Axes"])
        self.__tree.setItemDelegateForColumn(1, self.__axesDelegate)

        sourceTree = {}
        masterTree = {}

        if self.__scan is not None:
            for device in self.__scan.devices():
                if device.isMaster():
                    item = qt.QStandardItem("Master %s" % device.name())
                else:
                    item = qt.QStandardItem("Device %s" % device.name())
                masterTree[device] = item
                for channel in device.channels():
                    channelItem = qt.QStandardItem("Channel %s" % channel.name())
                    emptyItem = qt.QStandardItem("")
                    item.appendRow([channelItem, emptyItem])

                master = device.master()
                if master is None:
                    # Root device
                    parent = model
                else:
                    itemMaster = masterTree.get(master, None)
                    if itemMaster is None:
                        parent = model
                        print("Device list is not well ordered")
                    else:
                        parent = itemMaster

                emptyItem = qt.QStandardItem("")
                parent.appendRow([item, emptyItem])

        itemWithoutLocation = qt.QStandardItem("Not part of the scan")
        model.appendRow(itemWithoutLocation)

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
                parent = itemWithoutLocation

            axesItem = qt.QStandardItem("")
            if isinstance(
                plotItem,
                (plot_curve_model.CurveMixIn, plot_curve_model.CurveStatisticMixIn),
            ):
                axesItem.setData(plotItem, role=PlotItemData)
            parent.appendRow([item, axesItem])
            self.__tree.openPersistentEditor(axesItem.index())

        self.__tree.expandAll()
