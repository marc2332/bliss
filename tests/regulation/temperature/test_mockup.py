import pytest
import gevent
from unittest import mock
from bliss.common.regulation import SoftLoop
from bliss.common.scans import ascan, ct


def mockup_regulation(loop):
    x = loop

    info = x.__info__()
    info_i = x.input.__info__()
    info_o = x.output.__info__()

    kp = x.kp
    x.kp = kp + 0.1
    assert x.kp == kp + 0.1
    x.kp = kp

    ki = x.ki
    x.ki = ki + 0.1
    assert x.ki == ki + 0.1
    x.ki = ki

    kd = x.kd
    x.kd = kd + 0.1
    assert x.kd == kd + 0.1
    x.kd = kd

    rr = x.ramprate
    x.ramprate = rr + 0.1
    assert x.ramprate == rr + 0.1
    x.ramprate = rr

    # --- Soft loop params ------
    if isinstance(x, SoftLoop):
        spf = x.sampling_frequency
        x.sampling_frequency = spf + 1
        assert x.sampling_frequency == spf + 1
        x.sampling_frequency = spf
        assert x.sampling_frequency == spf

        pr = x.pid_range
        x.pid_range = (0, 1)
        assert x.pid_range == (0, 1)
        x.pid_range = pr
        assert x.pid_range == pr

    # ---- start/stop --------
    # -- no ramping (rate = 0)
    x.ramprate = 0
    sp = x.input.read() + 1.0
    x.setpoint = sp
    assert x.is_ramping() is False
    gevent.sleep(0.1)
    assert x.is_ramping() is False
    assert x.setpoint == sp

    # -- with ramping (rate != 0)
    x.ramprate = 1.0
    sp = x.input.read() + 1.0
    x.setpoint = sp
    assert x.is_ramping() is True
    gevent.sleep(0.1)
    assert x.is_ramping() is True
    with gevent.Timeout(3.0):
        # Takes approx. 1 seconds
        while x.is_ramping():
            gevent.sleep(0.01)
    assert x.setpoint == sp

    # -- interupt the ramping ----
    sp = x.input.read() + 1.0
    x.setpoint = sp
    gevent.sleep(0.1)
    assert x.is_ramping() is True
    x.stop()
    assert x.is_ramping() is False

    # ---- scanning ----------

    db = x.deadband
    x.deadband = db + 0.01
    assert x.deadband == db + 0.01
    x.deadband = db

    dif = x.deadband_idle_factor
    x.deadband_idle_factor = dif + 1
    assert x.deadband_idle_factor == dif + 1
    x.deadband_idle_factor = dif

    x.ramprate = 10.0
    x.deadband_time = 2.0
    x.wait_mode = "DEADBAND"
    sp = x.input.read() + 0.1
    x.axis_move(sp)

    with gevent.Timeout(10.0):
        # Takes approx. 5 seconds
        while x.axis_state() != "READY":
            gevent.sleep(0.01)

    assert x.setpoint == sp


def test_ct_scan_just_after_session_starts(default_session, temp_tloop):
    ct(0.1, temp_tloop)


def test_sampling_counter_input(default_session):
    din = default_session.config.get("diode_input")
    din.read()


def test_sample_regulation(temp_tloop):
    mockup_regulation(temp_tloop)


def test_soft_regulation(temp_soft_tloop):
    mockup_regulation(temp_soft_tloop)


def test_soft_regulation_2(temp_soft_tloop_2):
    mockup_regulation(temp_soft_tloop_2)


def test_soft_regulation_failure(temp_soft_tloop):
    loop = temp_soft_tloop
    assert loop.max_attempts_before_failure == 3

    # start regulation
    loop.setpoint = 1

    # count read attempts before failure
    with mock.patch.object(loop.input, "read", side_effect=Exception) as read:
        with pytest.raises(Exception):
            loop.task.get()
        assert read.call_count == loop.max_attempts_before_failure + 1

    # restart regulation
    loop.setpoint = 1

    # count set_value attempts before failure
    with mock.patch.object(
        loop.output, "set_value", side_effect=Exception
    ) as set_value:
        with pytest.raises(Exception):
            loop.task.get()
        assert set_value.call_count == loop.max_attempts_before_failure + 1


def test_regulation_plot(temp_tloop, flint_session):
    x = temp_tloop
    x.setpoint = 0
    plt = x.plot()
    plt.stop()
    gevent.sleep(1.0)
    plt.start()

    x.ramprate = 1.0
    sp = x.input.read() + 0.1
    # x.deadband_time = 2.0
    x.wait_mode = "RAMP"
    ascan(x.axis, sp, sp + 1, 10, 0.1, x)
