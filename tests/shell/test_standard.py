import subprocess
import time
import builtins
import pytest
import numpy
import psutil

from bliss.shell import standard
from bliss.shell.standard import wa, wm, sta, stm, _launch_silx, umv

from bliss.shell.standard import sin, cos, tan, arcsin, arccos, arctan, arctan2
from bliss.shell.standard import log, log10, sqrt, exp, power, deg2rad, rad2deg
from bliss.shell.standard import rand, date, sleep
from bliss.shell.standard import flint
from bliss.controllers.lima import roi as lima_rois


@pytest.fixture
def s1hg(default_session):
    s1hg = default_session.config.get("s1hg")
    yield s1hg
    s1hg.__close__()


def test_std_func():

    # No mathematical proof, just to ensure all functions are imported.
    numpy.testing.assert_almost_equal(sin(cos(tan(arcsin(0.1)))), 0.838733, 4)
    numpy.testing.assert_almost_equal(arccos(arctan(arctan2(0.1, 1))), 1.47129, 4)
    numpy.testing.assert_almost_equal(log(sqrt(exp(power(2, 3)))), 4.0, 4)
    numpy.testing.assert_almost_equal(log10(deg2rad(rad2deg(4))), 0.602, 4)

    _ = rand()
    _ = date()
    sleep(0.001)


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
    output += "Offset    0.0\n"
    output += "\n"
    output += "Dial\n"
    output += " High     inf\n"
    output += " Current  !ERR\n"
    output += " Low      -inf\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert errmsg in captured.err

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert errmsg in captured.err


def test_sta_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_state = False
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
    assert "s1f" not in captured.out
    assert "s1b" not in captured.out


def test_sta_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_state = True
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert errmsg in captured.err

    errmsg = "RuntimeError: Error on motor 'bad': BAD STATE"
    assert errmsg in captured.err


def test_stm_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_state = False
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_stm_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_state = True
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert errmsg in captured.err

    errmsg = "RuntimeError: Error on motor 'bad': BAD STATE"
    assert errmsg in captured.err


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
    with pytest.raises(RuntimeError):
        umv(1, m0)
    with pytest.raises(RuntimeError):
        umv()


def test_umv_signature(session):
    assert str(umv.__signature__) == "(*args: 'motor1, pos1, motor2, pos2, ...')"


@pytest.fixture
def capture_output_patch():
    orig_print = builtins.print
    from bliss.shell.cli.repl import CaptureOutput

    capout = CaptureOutput()
    capout.patch_print()
    yield
    builtins.print = orig_print


@pytest.mark.xfail()
def test_umv_shell(capfd, default_session, capture_output_patch):
    roby = default_session.config.get("roby")
    umv(roby, 1)
    output = capfd.readouterr().out.splitlines()
    # first 3 items are: empty line, motor name, empty line
    assert all(x != "" for x in output[3:])


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


def test_open_close_flint(test_session_without_flint):
    f = flint()
    assert f is not None
    pid = f.pid
    assert psutil.pid_exists(pid)
    f.close()
    process = psutil.Process(pid)
    psutil.wait_procs([process], timeout=1)
    assert not psutil.pid_exists(pid)


def test_open_kill_flint(test_session_without_flint):
    f = flint()
    assert f is not None
    pid = f.pid
    assert psutil.pid_exists(pid)
    f.kill9()
    process = psutil.Process(pid)
    psutil.wait_procs([process], timeout=1)
    assert not psutil.pid_exists(pid)


def test_edit_roi_counters(
    mocker, beacon, default_session, lima_simulator, test_session_with_flint
):
    # Mock few functions to coverage the code without flint
    roi1 = lima_rois.Roi(10, 11, 100, 101, name="roi1")
    roi2 = lima_rois.RoiProfile(20, 21, 200, 201, name="roi2", mode="vertical")
    plot_mock = mocker.Mock()
    plot_mock.select_shapes = mocker.Mock(return_value=[roi1, roi2])

    mocker.patch("bliss.common.plot.plot_image", return_value=plot_mock)

    cam = beacon.get("lima_simulator")

    cam.roi_counters.clear()
    cam.roi_profiles.clear()
    cam.roi_counters["foo1"] = 20, 20, 18, 20
    cam.roi_profiles["foo2"] = 20, 20, 18, 20, "vertical"
    standard.edit_roi_counters(cam)
    assert "roi1" in cam.roi_counters
    assert "roi2" in cam.roi_profiles
    plot_mock.select_shapes.assert_called_once()
    plot_mock.focus.assert_called_once()
