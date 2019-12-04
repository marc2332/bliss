from bliss.shell.interlocks import *


def test_interlock_show(default_session, wago_mockup, capsys):
    interlock_show()
    captured = capsys.readouterr()
    assert "No instance found" in captured.out
    wago_simulator = default_session.config.get("wago_simulator")
    interlock_show()
    captured = capsys.readouterr()
    assert "Interlock Firmware is not present in the PLC" in captured.out
    assert "2 interlock instance" in captured.out


def test_interlock_state(default_session, wago_mockup):
    interlock_state()
    wago_simulator = default_session.config.get("wago_simulator")
    assert interlock_state(wago_simulator) == {}
    assert interlock_state() == {}
