# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.actions import PlotAction
from silx.gui.plot.actions import control


_logger = logging.getLogger(__name__)


class CheckableKeepAspectRatioAction(PlotAction):
    """QAction controlling X axis log scale on a :class:`.PlotWidget`.

    :param plot: :class:`.PlotWidget` instance on which to operate
    :param parent: See :class:`QAction`
    """

    def __init__(self, plot, parent=None):
        super(CheckableKeepAspectRatioAction, self).__init__(
            plot,
            icon="shape-circle-solid",
            text="Keep aspect ratio",
            tooltip="Keep axes aspect ratio",
            triggered=self._actionTriggered,
            checkable=True,
            parent=parent,
        )
        self.setChecked(self.plot.isKeepDataAspectRatio())
        plot.sigSetKeepDataAspectRatio.connect(self._keepDataAspectRatioChanged)

    def _keepDataAspectRatioChanged(self, aspectRatio):
        """Handle Plot set keep aspect ratio signal"""
        self.setChecked(aspectRatio)

    def _actionTriggered(self, checked=False):
        self.plot.setKeepDataAspectRatio(checked)


class CustomAxisAction(qt.QWidgetAction):
    def __init__(self, plot, parent, kind="any"):
        super(CustomAxisAction, self).__init__(parent)

        menu = qt.QMenu(parent)

        action = control.ShowAxisAction(plot, self)
        action.setText("Show the plot axes")
        menu.addAction(action)

        if kind in ["curve", "scatter"]:
            menu.addSection("X-axes")
            action = control.XAxisLogarithmicAction(plot, self)
            action.setText("Log scale")
            menu.addAction(action)

        menu.addSection("Y-axes")
        if kind in ["curve", "scatter", "mca"]:
            action = control.YAxisLogarithmicAction(plot, self)
            action.setText("Log scale")
            menu.addAction(action)
        if kind in ["scatter", "image"]:
            action = control.YAxisInvertedAction(plot, self)
            menu.addAction(action)

        if kind in ["scatter", "image"]:
            menu.addSection("Aspect ratio")
            action = CheckableKeepAspectRatioAction(plot, self)
            action.setText("Keep aspect ratio")
            menu.addAction(action)

        action = control.GridAction(plot, "major", self)
        menu.addAction(action)

        icon = icons.getQIcon("flint:icons/axes-options")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Custom axis")
        toolButton.setToolTip("Custom the plot axis")
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)
