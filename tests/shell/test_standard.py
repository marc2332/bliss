import logging
import subprocess
import time

import pytest

from bliss.shell.standard import wa, wm, sta, stm, _launch_silx, umv


@pytest.fixture
def s1hg(default_session):
    s1hg = default_session.config.get("s1hg")
    yield s1hg
    s1hg.__close__()


def test_wa_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    wa()
    captured = capsys.readouterr()
    output = "Current Positions: user\n"
    output += "                   dial\n"
    output += "\n"
    output += "    bad\n"
    output += "-------\n"
    output += "0.00000\n"
    output += "0.00000\n"

    assert captured.out == output


def test_wa_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    wa()
    captured = capsys.readouterr()

    output = "Current Positions: user\n"
    output += "                   dial\n"
    output += "\n"
    output += "bad\n"
    output += "-----\n"
    output += "!ERR\n"
    output += "!ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg


def test_wa_slits(s1hg, capsys):
    wa()
    captured = capsys.readouterr()

    assert "s1hg" in captured.out
    assert not "s1f" in captured.out
    assert not "s1b" in captured.out


def test_wm_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    wm("bad")
    captured = capsys.readouterr()

    output = "\n"
    output += "              bad\n"
    output += "--------  -------\n"
    output += "User\n"
    output += " High         inf\n"
    output += " Current  0.00000\n"
    output += " Low         -inf\n"
    output += "Offset    0.00000\n"
    output += "\n"
    output += "Dial\n"
    output += " High         inf\n"
    output += " Current  0.00000\n"
    output += " Low         -inf\n"

    assert captured.out == output


def test_wm_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    wm("bad")
    captured = capsys.readouterr()

    output = "\n"
    output += "          bad\n"
    output += "--------  -----\n"
    output += "User\n"
    output += " High     inf\n"
    output += " Current  !ERR\n"
    output += " Low      -inf\n"
    output += "Offset    0\n"
    output += "\n"
    output += "Dial\n"
    output += " High     inf\n"
    output += " Current  !ERR\n"
    output += " Low      -inf\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


def test_sta_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_sta_slits(s1hg, capsys):
    sta()

    captured = capsys.readouterr()

    assert "s1hg" in captured.out
    assert not "s1f" in captured.out
    assert not "s1b" in captured.out


def test_sta_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


def test_stm_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_stm_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


def execute_in_subprocess(command):
    script = subprocess.Popen(
        ["python", "-c", command], stderr=subprocess.PIPE, stdout=subprocess.PIPE
    )

    output, err = script.communicate()
    returncode = script.returncode
    return output.decode(), err.decode(), returncode


def test_umv_typecheck(session):
    m0 = session.env_dict["m0"]

    umv(m0, 1.2)
    with pytest.raises(RuntimeError):
        umv(m0, 1, 2)
    with pytest.raises(TypeError):
        umv(1, m0)
    with pytest.raises(RuntimeError):
        umv()


def test_umv_signature(session):
    assert str(umv.__signature__) == "(*args: 'motor1, pos1, motor2, pos2, ...')"


def test_umvr_lib_mode(capsys, default_session):
    """lprint should not show anything"""

    commands = (
        "from bliss.shell.standard import umv",
        "from bliss.config import static",
        "config = static.get_config()",
        "roby = config.get('roby')",
        "umv(roby,10)",
    )

    output, err, returncode = execute_in_subprocess(";".join(commands))

    assert "Moving," not in output
    assert "MockupAxis" not in output

    assert returncode == 0
    assert len(err) == 0


def test_sync_lib_mode(capsys, default_session):
    """lprint should not show anything"""
    commands = (
        "from bliss.shell.standard import sync",
        "from bliss.config import static",
        "config = static.get_config()",
        "roby = config.get('roby')",
        "sync(roby)",
    )

    output, err, returncode = execute_in_subprocess(";".join(commands))

    assert "Forcing axes synchronization with hardware" not in output

    assert returncode == 0
    assert len(err) == 0


def test_open_silx(xvfb):
    # checking if the process opens without stdout errors
    process = _launch_silx()
    time.sleep(1)
    assert process.returncode is None
    process.terminate()
