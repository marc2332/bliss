# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Check box displayed using a look and feel of an eye"""

from silx.gui import qt
from silx.gui import icons


class EyeCheckBox(qt.QCheckBox):
    def __init__(self, parent: qt.QWidget = None):
        qt.QCheckBox.__init__(self, parent=parent)

        # FIXME remove the hardcoded size, rework the icon and use size.height as a constraint
        size = self.sizeHint() + qt.QSize(5, 5)
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
        self.setStyleSheet(style)
