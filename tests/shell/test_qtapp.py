from bliss import current_session
from bliss.shell.qtapp.tweak_ui import TweakUI
from bliss.common.axis import Axis
from bliss.common import scans
from bliss.shell.standard import mvr
import unittest
from unittest.mock import patch
import pytest
import time
from PyQt5 import Qt as qt

app = None


@pytest.mark.usefixtures("xvfb", "session")
class TweakUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        global app
        app = qt.QApplication.instance()
        if app is None:
            app = qt.QApplication([])

    def setUp(self) -> None:
        self.window = TweakUI(["m0"], current_session.name)
        self.window.combo_h.setCurrentIndex(1)

    def test_defaults(self):
        self.assertEqual(self.window.index["m0"]["step"].text(), "1.0")
        self.assertEqual("m0", self.window.combo_h.currentText())
        self.assertEqual(
            str(self.window.motor_h.position),
            self.window.index["m0"]["position"].text(),
        )

    def test_move(self):
        pos_initial = self.window.motor_h.position
        self.window.btn_right.click()
        time.sleep(2)
        self.assertEqual(pos_initial + 1, self.window.motor_h.position)

    def test_ct(self):
        with patch.object(TweakUI, "startCt") as ct_auto:
            window = TweakUI(["m0"], current_session.name)
            window.combo_h.setCurrentIndex(1)
            window.ctButton.click()
            mvr(window.motors.motors[0], 1)
            time.sleep(2)
            self.assertEqual(0, ct_auto.call_count)
            window.btn_right.click()
            time.sleep(2)
            self.assertEqual(3, ct_auto.call_count)
            window.close()

    def test_state(self):
        self.assertIn("READY", self.window.motor_h.state)
        with patch.object(Axis, "state", "MOVING"):
            self.window.changeColor(self.window.motor_h, self.window.motor_h.state)
            self.assertIn("MOVING", self.window.motor_h.state)
            self.assertEqual(
                self.window.index["m0"]["position"]
                .palette()
                .color(qt.QPalette.Background)
                .red(),
                128,
            )
            self.assertEqual(
                self.window.index["m0"]["position"]
                .palette()
                .color(qt.QPalette.Background)
                .green(),
                160,
            )
            self.assertEqual(
                self.window.index["m0"]["position"]
                .palette()
                .color(qt.QPalette.Background)
                .blue(),
                255,
            )

    def tearDown(self) -> None:
        self.window.close()


if __name__ == "__main__":
    unittest.main()
