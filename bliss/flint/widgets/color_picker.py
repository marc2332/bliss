# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Color picker for flint"""


from silx.gui import qt


class ColorEditor(qt.QLineEdit):
    def __init__(self, parent=None):
        super(ColorEditor, self).__init__(parent=parent)

    def getColor(self):
        text = self.text().strip()
        if text == "":
            return qt.QColor()
        else:
            try:
                return qt.QColor(text)
            except Exception:
                return qt.QColor()

    def setColor(self, color):
        self.setText(color.name())

    color = qt.Property(qt.QColor, getColor, setColor, user=True)


class ColorPicker(qt.QComboBox):
    def __init__(self, parent: qt.QWidget):
        super(ColorPicker, self).__init__(parent=parent)
        editor = ColorEditor(self)
        editor.setReadOnly(True)
        self.setLineEdit(editor)

    def _createColorIcon(self, color: qt.QColor):
        pixmap = qt.QPixmap(32, 32)
        pixmap.fill(color)
        icon = qt.QIcon(pixmap)
        return icon

    def addColor(self, label, color: qt.QColor):
        self.addItem(label, color)
        if color is None or not color.isValid():
            color = qt.QColor(220, 220, 220)
        icon = self._createColorIcon(color)
        self.setItemIcon(self.count() - 1, icon)

    def currentColor(self) -> qt.QColor:
        index = self.currentIndex()
        return self.itemData(index)

    def setCurrentColor(self, color: qt.QColor):
        for index in range(self.count()):
            if color == self.itemData(index):
                self.setCurrentIndex(index)
                return
        if color is None:
            # If None was not a value
            self.setCurrentIndex(-1)
            return
        self.addItem("Custom", color)
        self.setCurrentIndex(self.count() - 1)
