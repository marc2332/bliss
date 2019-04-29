# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys
import logging

try:
    import pyqtconsole.console
except ImportError:
    pyqtconsole = None

from PyQt4 import Qt

from bliss.controllers.ct2 import card as card_module


_FMT = """\
<span style="color:{color}; white-space: nowrap;">%(levelname)07s </span>\
<span style="font-weight: bold; white-space: nowrap;">%(name)s </span>\
<span>%(message)s</span>\
"""


class Handler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.__log_widget = kwargs.pop("widget")
        logging.Handler.__init__(self, *args, **kwargs)
        self.setFormatter(logging.Formatter(_FMT))

    def emit(self, record):
        text = self.format(record)
        color = "black"
        if record.levelno >= logging.ERROR:
            color = "red"
        elif record.levelno >= logging.WARNING:
            color = "orange"
        elif record.levelno < logging.INFO:
            color = "gray"
        text = text.format(color=color)
        self.__log_widget.appendHtml(text)


class Label(Qt.QLabel):
    def __init__(self, *args, **kargs):
        super(Label, self).__init__(*args, **kargs)
        f = self.font()
        f.setFamily("Monospace")
        self.setFont(f)


class CtPanel(Qt.QWidget):

    LabelColumn = 0
    CounterColumn = 1
    LatchColumn = 2
    SoftwareStart = 3

    def __init__(self, *args, **kwargs):
        counters = kwargs.pop("counters", 0)
        super(CtPanel, self).__init__(*args, **kwargs)
        layout = Qt.QGridLayout(self)
        self.setCounterNb(counters)

    def setCounterNb(self, n):
        layout = self.layout()
        while layout.count():
            layout.takeAt(0)
        for row in range(n):
            ct = row + 1
            layout.addWidget(Qt.QLabel("Ct {0}:".format(ct)), row, self.LabelColumn)
            layout.addWidget(Label("-----"), row, self.CounterColumn)
            layout.addWidget(Label("-----"), row, self.LatchColumn)
            cb = Qt.QCheckBox()
            cb.setToolTip("Start on Software Start")
            layout.addWidget(cb, row, self.SoftwareStart)

    def refresh(self, counters=None, latches=None):
        layout = self.layout()
        row_nb = layout.rowCount()
        if not counters is None:
            assert len(counters) == row_nb
            for row in range(row_nb):
                lbl = layout.itemAtPosition(row, self.CounterColumn).widget()
                lbl.setText("{0}".format(counters[row]))
        if not latches is None:
            assert len(latches) == row_nb
            for row in range(row_nb):
                lbl = layout.itemAtPosition(row, self.LatchColumn).widget()
                lbl.setText("{0}".format(latches[row]))

    def getStartCounters(self):
        layout = self.layout()
        result = []
        for row in range(layout.rowCount()):
            cb = layout.itemAtPosition(row, self.SoftwareStart).widget()
            if cb.isChecked():
                result.append(row + 1)
        return result


class CT2Window(Qt.QMainWindow):
    def __init__(self, *args, **kwargs):
        self.__card = None
        self.__console = None
        card = kwargs.pop("card", None)
        refresh = kwargs.pop("refresh", 0)

        super(CT2Window, self).__init__(*args, **kwargs)

        widget = Qt.QWidget(self)
        self.setCentralWidget(widget)
        layout = Qt.QGridLayout(widget)
        ct_latch_gb = Qt.QGroupBox("Counters && Latches")
        ct_latch_gb_layout = Qt.QVBoxLayout(ct_latch_gb)
        layout.addWidget(ct_latch_gb)

        self.__ct_panel = CtPanel()
        ct_latch_gb_layout.addWidget(self.__ct_panel)

        tb = self.addToolBar("main")

        self.__refresh_widget = rw = Qt.QDoubleSpinBox()
        rw.setToolTip("refresh period (s)")
        rw.setDecimals(3)
        rw.setRange(0, 10)
        rw.setPrefix("refresh ")
        rw.setSuffix(" s")
        rw.setSingleStep(0.05)
        rw.setSpecialValueText("no refresh")
        rw.valueChanged.connect(self.__onChangeRefreshPeriod)
        tb.addWidget(rw)

        icon = Qt.QIcon.fromTheme("view-refresh")

        self.__refresh_timer = Qt.QTimer()
        self.__refresh_timer.timeout.connect(self.__onRefresh)

        self.__start = tb.addAction("soft. start")
        self.__start.setToolTip("Software start of selected counters")
        self.__start.triggered.connect(self.__onSoftwareStart)

        self.__stop = tb.addAction("soft. stop")
        self.__stop.setToolTip("Software stop of ALL counters")
        self.__stop.triggered.connect(self.__onSoftwareStop)

        self.__software_reset = tb.addAction("soft. reset")
        self.__software_reset.triggered.connect(self.__onSoftwareReset)

        self.__reset = tb.addAction("reset")
        self.__reset.triggered.connect(self.__onReset)

        self.__exclusive = tb.addAction(icon, "exclusive access")
        self.__exclusive.setCheckable(True)
        self.__exclusive.toggled.connect(self.__onExclusive)

        self.__reconfig = tb.addAction(icon, "reconfig")
        self.__reconfig.triggered.connect(self.__onReconfigure)

        self.setCard(card)
        self.setRefreshPeriod(refresh)

        self.__log_widget = Qt.QPlainTextEdit()
        self.__log_widget.setStyleSheet(".QPlainTextEdit {font-family: Monospace}")
        self.__log_handler = Handler(widget=self.__log_widget)
        logging.getLogger().addHandler(self.__log_handler)
        self.__log_dock = Qt.QDockWidget("logging")
        self.__log_dock.setWidget(self.__log_widget)
        self.addDockWidget(Qt.Qt.BottomDockWidgetArea, self.__log_dock)

    def __addConsole(self):
        self.__console = pyqtconsole.console.PythonConsole(local={"card": self.__card})
        self.__console_dock = Qt.QDockWidget("console")
        self.__console_dock.setWidget(self.__console)
        self.addDockWidget(Qt.Qt.BottomDockWidgetArea, self.__console_dock)

    def setCard(self, card):
        if card == self.__card:
            return
        self.__card = card
        if card is None:
            counters = 0
            title = "ct2 - disconnected"
        else:
            counters = len(card.COUNTERS)
            title = "ct2 - {0} ({1})".format(card.name, card.address)
            # Only add console after the card has been added
            # in order for it to have the card as local
            if self.__console is None and pyqtconsole:
                self.__addConsole()
        self.__ct_panel.setCounterNb(counters)
        self.setWindowTitle(title)
        self.__updateGUIStatus()

    def setRefreshPeriod(self, period):
        self.__refresh_widget.setValue(period)

    def __onChangeRefreshPeriod(self, period):
        if period < 0.001:
            self.__refresh_timer.stop()
        else:
            self.__refresh_timer.start(int(period * 1000))

    def __onRefresh(self):
        if self.__card is None:
            return
        counters = self.__card.get_counters_values()
        latches = self.__card.get_latches_values()
        self.__ct_panel.refresh(counters, latches)

    def __updateGUIStatus(self):
        enable = not self.__card is None
        for w in (
            self.__start,
            self.__stop,
            self.__software_reset,
            self.__reset,
            self.__exclusive,
            self.__reconfig,
        ):
            w.setEnabled(enable)
        if self.__card:
            self.__exclusive.setChecked(self.__card.has_exclusive_access())

    def __onSoftwareStart(self):
        if self.__card is None:
            return
        # start on selected counters
        counters = self.__ct_panel.getStartCounters()
        self.__card.start_counters_software(counters)

    def __onSoftwareStop(self):
        if self.__card is None:
            return
        # stop on all counters
        self.__card.stop_counters_software(self.__card.COUNTERS)

    def __onSoftwareReset(self):
        self.__card.software_reset()

    def __onReset(self):
        self.__card.reset()

    def __onExclusive(self, exclusive):
        if exclusive:
            self.__card.request_exclusive_access()
        else:
            self.__card.relinquish_exclusive_access()

    def __onReconfigure(self):
        card = self.__card
        cfg = get_config(reload=True)
        if card is None:
            return
        card.request_exclusive_access()
        card.set_interrupts()
        card.reset_FIFO_error_flags()
        card.reset()
        card.software_reset()
        card_cfg = cfg.get_config(self.__card.name)
        ct2_module.configure_card(self.__card, card_cfg)


def get_config(reload=False):
    global __config
    try:
        cfg = __config
        if reload:
            cfg.reload()
        return cfg
    except NameError:
        from bliss.config.static import get_config

        __config = get_config()
    return __config


def get_card_config(name):
    return get_config().get_config(name)


def GUI():
    window = CT2Window()
    window.show()
    return window


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ct2 GUI")
    parser.add_argument(
        "--card", type=str, default="p201", help="name of the card in the configuration"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        help="log level (debug, info, warning, error) [default: info]",
    )
    parser.add_argument("--refresh", type=float, default=0.2, help="refresh period (s)")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = Qt.QApplication([])
    window = CT2Window()
    window.show()

    card_config = get_card_config(args.card)
    card = ct2_module.create_and_configure_card(card_config)
    card.name = args.card

    window.setCard(card)
    window.setRefreshPeriod(args.refresh)

    app.exec_()


if __name__ == "__main__":
    main()
