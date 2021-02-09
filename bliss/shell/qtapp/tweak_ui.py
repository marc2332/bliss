# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import math
import os
import contextlib
import tempfile
import logging
import argparse
from silx.gui import qt
from PyQt5 import uic
from bliss.flint.flint import patch_qt
from bliss.shell.standard import mv, mvr
from bliss.config.static import get_config
from functools import partial
from bliss.comm import rpc
from bliss.shell.qtapp.resources import get_resource
import gevent
from bliss.common import event
from bliss.common.event import connect, disconnect
from bliss.config.conductor.client import get_redis_proxy

_logger = logging.getLogger(__name__)


triggerCounter = False


class ContextTrigger(object):
    def __enter__(self):
        global triggerCounter
        triggerCounter = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        global triggerCounter
        triggerCounter = False


class GroupMotors(qt.QObject):
    moving = qt.Signal(bool)

    def __init__(self):
        super(GroupMotors, self).__init__()
        self.movingMotors = 0
        self.motors = []
        self.index = dict()

    def enumerate(self):
        return enumerate(self.motors)

    def addMotor(self, motor):
        connect(motor, "state", self.updateGroupState)
        self.index[motor.name] = motor.state
        self.motors.append(motor)

    def removeMotors(self):
        for motor in self.motors:
            disconnect(motor, "state", self.updateGroupState)

    def updateGroupState(self, state, sender):
        global triggerCounter
        if sender.name in self.index and triggerCounter:
            if "MOVING" in state:
                self.movingMotors += 1
                self.moving.emit(True)
            else:
                self.movingMotors -= 2
                if self.movingMotors == 0:
                    self.moving.emit(False)


class MotorPosition(qt.QLineEdit):
    def __init__(self):
        super(MotorPosition, self).__init__()
        self.motor = None

    def setMotor(self, motor):
        self.motor = motor
        digit = abs(int(math.log10(motor.tolerance)))
        doubleValidator = qt.QDoubleValidator(motor.low_limit, motor.high_limit, digit)
        self.setValidator(doubleValidator)
        self.setText(str(self.motor.position))
        self.returnPressed.connect(partial(self.startMovePosition, motor))
        self.setAlignment(qt.Qt.AlignRight)

    def focusOutEvent(self, event: qt.QFocusEvent) -> None:
        super(MotorPosition, self).focusOutEvent(event)
        self.setText(str(self.motor.position))

    def startMovePosition(self, motor):
        gevent.spawn(self.moveToPosition, motor)

    def moveToPosition(self, motor):
        with ContextTrigger():
            new_pos = float(self.text())
            mv(motor, new_pos)


class TweakUI(qt.QMainWindow):
    """
    Graphical user interface to move motors
    """

    def __init__(self, motors, session):
        super(TweakUI, self).__init__()
        self.loaded = False
        self.close_new = False
        self.session = session
        uic.loadUi(get_resource("ui/tw_design.ui"), self)  # Load the .ui file
        self.setWindowTitle(f"Tweak Motors UI [{self.session}]")
        self.setWindowIcon(qt.QIcon(get_resource("logo/bliss_logo_small.svg")))
        self.cfg = get_config()
        self.motors = GroupMotors()
        self.index = dict()
        if isinstance(motors, list):
            for motor in motors:
                self.addMotor(motor)
        else:
            self.addMotor(motors)

        self.motor_h, self.motor_v = None, None
        self.prev_state_h, self.prev_state_v = "", ""
        self.fill()
        self.motors.moving.connect(self.startCt)

        self.timer = qt.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.RestartEvent)
        self.timer.start()

        self.createActions()
        self.show()  # Show the GUI
        self.loaded = True

    def closeEvent(self, event: qt.QCloseEvent) -> None:
        self.motors.removeMotors()
        for motor in self.motors.motors:
            self.removeMotor(motor)

    def addMotor(self, motor):
        motor = self.cfg.get(motor)
        self.motors.addMotor(motor)
        connect(motor, "position", self.updateMotorPosition)
        connect(motor, "state", self.updateMotorState)

    def removeMotor(self, motor):
        disconnect(motor, "position", self.updateMotorPosition)
        disconnect(motor, "state", self.updateMotorState)

    def checkEmpty(self, line):
        if str(line.text()) == "":
            line.setStyleSheet("""QLineEdit { background-color: red;}""")
        else:
            line.setStyleSheet("""QLineEdit { background-color: white;}""")
        qt.QApplication.processEvents()

    def fill(self):
        self.combo_h.addItem("")
        self.combo_v.addItem("")
        for i, motor in self.motors.enumerate():
            n = motor.name
            step = qt.QLineEdit("1")
            step_validator = qt.QDoubleValidator(0, 9000, 3)
            step.setValidator(step_validator)
            step.textChanged.connect(partial(self.checkEmpty, step))
            self.combo_h.addItem(motor.name)
            self.combo_v.addItem(motor.name)
            label = qt.QLabel(n)
            label.setAlignment(qt.Qt.AlignTop)
            self.gridLayout.addWidget(label, i + 1, 0)
            step.setAlignment(qt.Qt.AlignRight)
            position = MotorPosition()
            position.setMotor(motor)
            self.gridLayout.addWidget(position, i + 1, 1)
            unit = motor.unit if motor.unit is not None else ""
            self.gridLayout.addWidget(qt.QLabel(unit), i + 1, 2)
            self.gridLayout.addWidget(step, i + 1, 3)

            btn_plus = qt.QPushButton("+")
            btn_plus.setFixedWidth(25)
            btn_plus.clicked.connect(partial(self.startIncrease, motor))
            btn_minus = qt.QPushButton("-")
            btn_minus.setFixedWidth(25)
            btn_minus.clicked.connect(partial(self.startDecrease, motor))

            self.gridLayout.addWidget(step, i + 1, 3)
            self.gridLayout.addWidget(btn_plus, i + 1, 4)
            self.gridLayout.addWidget(btn_minus, i + 1, 5)

            self.index[n] = {"position": position, "step": step}
            self.changeColor(motor, motor.state)

        self.combo_h.currentIndexChanged.connect(partial(self.update, False))
        self.combo_v.currentIndexChanged.connect(partial(self.update, True))

        self.btn_left.clicked.connect(partial(self.startMove, -1, False))
        self.btn_right.clicked.connect(partial(self.startMove, 1, False))
        self.btn_up.clicked.connect(partial(self.startMove, 1, True))
        self.btn_down.clicked.connect(partial(self.startMove, -1, True))

        acq_validator = qt.QDoubleValidator(0, 9000, 3)
        self.acquisitionLine.setValidator(acq_validator)
        self.acquisitionLine.textChanged.connect(
            partial(self.checkEmpty, self.acquisitionLine)
        )

    def getPID(self):
        return os.getpid()

    def update(self, vertical):
        if vertical:
            if self.combo_v.currentText() != "":
                self.motor_v = self.cfg.get(self.combo_v.currentText())
            else:
                self.motor_v = None
        else:
            if self.combo_h.currentText() != "":
                self.motor_h = self.cfg.get(self.combo_h.currentText())
            else:
                self.motor_h = None

    def RestartEvent(self):
        if self.close_new:
            self.close()

    def updateMotorPosition(self, position, sender):
        if sender.name in self.index:
            self.index[sender.name]["position"].setText(str(sender.position))

    def updateMotorState(self, state, sender):
        if sender.name in self.index:
            self.changeColor(sender, state)

    def startCt(self, moving):
        if not moving and self.ctButton.isChecked():
            if self.acquisitionLine.text() == "":
                self.acquisitionLine.setText("1")
            acq_time = float(self.acquisitionLine.text())
            event.send(self, "ct_requested", acq_time)

    def changeColor(self, motor, state):
        line = self.index[motor.name]["position"]
        if "MOVING" in state:
            line.setStyleSheet("background-color: rgb(128,160,255);")
            line.setText(f"{motor.position:.2f}")
        elif "READY" in state:
            line.setStyleSheet("background-color: rgb(255,255,255);")
        else:
            line.setStyleSheet("background-color: (255,0,0);")
        qt.QApplication.processEvents()

    def createActions(self):
        left = qt.QAction(self.btn_left)
        left.triggered.connect(self.btn_left.click)
        left.setShortcut("Left")

        right = qt.QAction(self.btn_right)
        right.triggered.connect(self.btn_right.click)
        right.setShortcut("Right")

        up = qt.QAction(self.btn_up)
        up.triggered.connect(self.btn_up.click)
        up.setShortcut("Up")

        down = qt.QAction(self.btn_down)
        down.triggered.connect(self.btn_down.click)
        down.setShortcut("Down")

        self.addAction(left)
        self.addAction(right)
        self.addAction(up)
        self.addAction(down)

    def increase(self, motor):
        with ContextTrigger():
            if self.index[motor.name]["step"].text() != "":
                step = float(self.index[motor.name]["step"].text())
                mvr(motor, step)

    def decrease(self, motor):
        with ContextTrigger():
            if self.index[motor.name]["step"].text() != "":
                step = float(self.index[motor.name]["step"].text())
                mvr(motor, -step)

    def move(self, sign, vertical):
        with ContextTrigger():
            try:
                if vertical and self.motor_v:
                    n = self.motor_v.name
                    if self.index[n]["step"].text() != "":
                        step = float(self.index[n]["step"].text())
                        mvr(self.motor_v, step * sign)
                elif not vertical and self.motor_h:
                    n = self.motor_h.name
                    if self.index[n]["step"].text() != "":
                        step = float(self.index[n]["step"].text())
                        mvr(self.motor_h, step * sign)
            except RuntimeError:
                sys.excepthook(*sys.exc_info())

    def startIncrease(self, motor):
        gevent.spawn(self.increase, motor)

    def startDecrease(self, motor):
        gevent.spawn(self.decrease, motor)

    def startMove(self, sign, vertical):
        gevent.spawn(self.move, sign, vertical)


@contextlib.contextmanager
def safe_rpc_server(obj):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        url = "ipc://{}".format(f.name)
        server = rpc.Server(obj, stream=True)
        try:
            server.bind(url)
            task = gevent.spawn(server.run)
            yield task, url
            task.kill()
            task.join()
        except Exception:
            _logger.error("Exception while serving %s", url, exc_info=True)
            raise
        finally:
            server.close()


@contextlib.contextmanager
def maintain_value(key, value):
    redis = get_redis_proxy()
    redis.lpush(key, value)
    yield
    redis.delete(key)


class TweakServer:
    def __init__(self, tweak):
        self.stop = gevent.event.AsyncResult()
        self.task = gevent.spawn(self._task, tweak, self.stop)
        self.task.link_exception(self.exception_orrured)

    def exception_orrured(self, future_exception):
        try:
            future_exception.get()
        except Exception:
            _logger.error("Error occurred in watch_session_scans", exc_info=True)

    def _task(self, tweak, stop):
        key = "tweak_ui_" + tweak.session
        with safe_rpc_server(tweak) as (task, url):
            with maintain_value(key, url):
                gevent.wait([stop, task], count=1)

    def join(self):
        self.stop.set_result(True)
        self.task.join()


def main(motors=None, session=None):
    patch_qt()
    app_tw = qt.QApplication(sys.argv)
    settings = qt.QSettings("ESRF", f"tweak_ui_{session}")
    gevent_timer = qt.QTimer()
    gevent_timer.start()
    gevent_timer.timeout.connect(partial(gevent.sleep, 0.01))

    local = qt.QLocale.c()
    local.setNumberOptions(local.numberOptions() | qt.QLocale.RejectGroupSeparator)
    qt.QLocale.setDefault(local)

    tweak = TweakUI(motors, session)
    geometry = settings.value("window_location", qt.QRect(), qt.QRect)
    if geometry.isValid():
        tweak.setGeometry(geometry)
    server = TweakServer(tweak)
    app_tw.exec_()
    settings.setValue("window_location", tweak.geometry())
    server.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--motors", nargs="+")
    parser.add_argument("--session")
    args = parser.parse_args()
    main(args.motors, args.session)
