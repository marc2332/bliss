# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import logging

from silx.gui import qt
from silx.gui import icons

from silx.gui.widgets.FloatEdit import FloatEdit
from bliss.flint.manager import monitoring

_logger = logging.getLogger(__name__)


class _GridLayout(qt.QGridLayout):
    def addRow(self, *widgets):
        layout = self.layout()
        row = layout.rowCount()
        if len(widgets) == 1:
            layout.addWidget(widgets[0], row, 0, 1, 3)
        elif len(widgets) == 3:
            layout.addWidget(widgets[0], row, 0)
            layout.addWidget(widgets[1], row, 1)
            layout.addWidget(widgets[2], row, 2)
        else:
            assert False


class _CustomEditorWidget(qt.QWidgetAction):
    """A GUI to custom video live"""

    executed = qt.Signal()

    def __init__(self, parent, scan):
        qt.QWidgetAction.__init__(self, parent)
        self.__scan = scan
        widget = qt.QWidget(parent)
        self.setDefaultWidget(widget)
        layout = _GridLayout(widget)

        label = qt.QLabel(widget)
        label.setAlignment(qt.Qt.AlignCenter)
        button = qt.QPushButton(widget)
        if scan.isLive():
            label.setText("Device in live")
            button.setText("Pause")
            button.clicked.connect(self.__stopLive)
            iconName = qt.QStyle.SP_MediaPause
        else:
            label.setText("Device in pause")
            button.setText("Live")
            button.clicked.connect(self.__startLive)
            iconName = qt.QStyle.SP_MediaPlay
        icon = widget.style().standardIcon(iconName)
        button.setIcon(icon)

        layout.addRow(label)
        layout.addRow(button)

        proxy = scan.getProxy()
        exposure_time = proxy.acq_expo_time
        latency_time = proxy.latency_time
        duration_time = exposure_time + latency_time

        def integerize(value):
            """Return a normalized value including if it was normalized"""
            integer = int(value)
            return integer, abs(integer - value) > 0.0001

        period, normalized = integerize(duration_time * 1000)
        about = "≈ " if normalized else ""
        toolTip = (
            "Time between 2 consecutive acquisitions "
            + "(exposition + dead time), in milliseconds"
        )
        periodValue = qt.QLabel(widget)
        periodValue.setAlignment(qt.Qt.AlignRight)
        periodValue.setText(f"{about}{period}")
        periodLabel = qt.QLabel(widget)
        periodLabel.setText("Period:")
        periodLabel.setToolTip(toolTip)
        periodUnit = qt.QLabel(widget)
        periodUnit.setText("ms")
        periodUnit.setToolTip(toolTip)
        layout.addRow(periodLabel, periodValue, periodUnit)

        if duration_time != 0:
            rate = 1 / (duration_time)
            rate, normalized = integerize(rate * 10)
            if rate >= 0.9:
                rate = rate / 10
                about = "≈ " if normalized else ""
                toolTip = "Number of acquisitions per seconds, in hertz"
                rateValue = qt.QLabel(widget)
                rateValue.setAlignment(qt.Qt.AlignRight)
                rateValue.setText(f"{about}{rate:0.1f}")
                rateLabel = qt.QLabel(widget)
                rateLabel.setText("Rate:")
                rateLabel.setToolTip(toolTip)
                rateUnit = qt.QLabel(widget)
                rateUnit.setText("Hz")
                rateUnit.setToolTip(toolTip)
                layout.addRow(rateLabel, rateValue, rateUnit)

        toolTip = "Exposition for a single acquisition, in milliseconds"
        exposureValue = FloatEdit(widget)
        exposureValue.editingFinished.connect(self.__updateExposure)
        exposureValue.setValue(int(exposure_time * 1000))
        exposureLabel = qt.QLabel(widget)
        exposureLabel.setText("Exposure time:")
        exposureLabel.setToolTip(toolTip)
        exposureUnit = qt.QLabel(widget)
        exposureUnit.setText("ms")
        exposureUnit.setToolTip(toolTip)
        layout.addRow(exposureLabel, exposureValue, exposureUnit)

        self.__exposure = exposureValue

    def __exceptionOrrured(self, future_exception):
        try:
            future_exception.get()
        except Exception:
            _logger.error("Error while executing greenlet", exc_info=True)

    def __updateExposure(self):
        exposure = self.__exposure.value() / 1000
        # Avoid to receive a second event (cause the menu is closed at the same time)
        self.__exposure.editingFinished.disconnect(self.__updateExposure)

        def execute():
            _logger.debug("Set lima exposure")
            live = self.__scan.isLive()
            proxy = self.__scan.getProxy()
            if live:
                proxy.video_live = False
                gevent.sleep(0.1)
            proxy.acq_expo_time = exposure
            if live:
                gevent.sleep(0.1)
                proxy.video_live = True

        task = gevent.spawn(execute)
        task.link_exception(self.__exceptionOrrured)
        self.executed.emit()

    def __startLive(self):
        proxy = self.__scan.getProxy()

        def execute():
            _logger.debug("Start lima video live")
            proxy.video_live = True

        task = gevent.spawn(execute)
        task.link_exception(self.__exceptionOrrured)
        self.executed.emit()

    def __stopLive(self):
        proxy = self.__scan.getProxy()

        def execute():
            _logger.debug("Stop lima video live")
            proxy.video_live = False

        task = gevent.spawn(execute)
        task.link_exception(self.__exceptionOrrured)
        self.executed.emit()


class CameraLiveAction(qt.QWidgetAction):
    def __init__(self, parent):
        super(qt.QWidgetAction, self).__init__(parent)

        tool = qt.QToolButton(parent)
        tool.setToolTip("Lima monitoring")
        self.__tool = tool
        self.__scan = None
        menu = qt.QMenu(parent)
        menu.aboutToShow.connect(self.__feedMenu)
        tool.setMenu(menu)
        tool.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(self.__tool)
        self.__update()

    def __feedMenu(self):
        menu = self.sender()
        menu.clear()
        editor = _CustomEditorWidget(self.defaultWidget(), self.__scan)
        editor.executed.connect(self.__closeMenu)
        menu.addAction(editor)

    def __closeMenu(self):
        menu = self.__tool.menu()
        menu.close()

    def setScan(self, scan):
        if not isinstance(scan, monitoring.MonitoringScan):
            scan = None
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.cameraStateChanged.disconnect(self.__updateIcon)
            self.__scan.scanFinished.disconnect(self.__finished)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.cameraStateChanged.connect(self.__updateIcon)
            self.__scan.scanFinished.connect(self.__finished)
        self.__update()

    def __finished(self):
        self.setScan(None)

    def __updateIcon(self):
        if self.__scan is None:
            iconName = "flint:icons/camera-none"
        elif self.__scan.isLive():
            iconName = "flint:icons/camera-live"
        else:
            iconName = "flint:icons/camera-pause"
        icon = icons.getQIcon(iconName)
        self.__tool.setIcon(icon)

    def __update(self):
        if self.__scan is None:
            self.__tool.setEnabled(False)
        else:
            self.__tool.setEnabled(True)
        self.__updateIcon()
