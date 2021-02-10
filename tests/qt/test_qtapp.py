from bliss.shell.standard import mvr
from bliss.common.axis import Axis
from bliss.shell.qtapp.tweak_ui import TweakUI
from silx.gui import qt
from unittest.mock import patch
import time


def test_qtapp(default_session, qapp):

    with patch.object(TweakUI, "startCt") as ct_auto:
        window = TweakUI(motors="m0", session=default_session.name)
        window.combo_h.setCurrentIndex(1)
        window.ctButton.click()

        # Default
        assert window.index["m0"]["step"].text() == "1"
        assert "m0" == window.combo_h.currentText()
        assert "READY" in window.motor_h.state

        # Motor move and ct
        mvr(window.motors.motors[0], 1)
        assert 0 == ct_auto.call_count

        pos_initial = window.motor_h.position
        window.btn_right.click()
        time.sleep(2)
        assert pos_initial + 1 == window.motor_h.position
        assert 3 == ct_auto.call_count

        # color
        with patch.object(Axis, "state", "MOVING"):
            window.changeColor(window.motor_h, window.motor_h.state)
            assert "MOVING" in window.motor_h.state
            assert (
                window.index["m0"]["position"]
                .palette()
                .color(qt.QPalette.Background)
                .red()
                == 128
            )
            assert (
                window.index["m0"]["position"]
                .palette()
                .color(qt.QPalette.Background)
                .green()
                == 160
            )
            assert (
                window.index["m0"]["position"]
                .palette()
                .color(qt.QPalette.Background)
                .blue()
                == 255
            )

        window.close()
