# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import pytest
from unittest import mock
from bliss.common import cleanup
from bliss.common.cleanup import capture_exceptions


def test_motor_stop_movement_cleanup(robz):
    pos = robz.position
    with cleanup.cleanup(robz):
        robz.rmove(1, wait=False)
    assert robz.state.READY
    assert robz.position != pos + 1


def test_motor_wait_restore_speed(robz, roby):
    previous_robz = robz.velocity
    previous_roby = roby.velocity
    with cleanup.cleanup(robz, roby, restore_list=(cleanup.axis.VEL,)):
        robz.velocity = 1002.121
        roby.velocity = 2.432
    assert robz.velocity == previous_robz
    assert roby.velocity == previous_roby


def test_motor_wait_restore_acceleration(robz):
    previous_robz = robz.acceleration
    with cleanup.cleanup(robz, restore_list=(cleanup.axis.ACC,)):
        robz.acceleration = 1002.121
    assert robz.acceleration == previous_robz


def test_motor_wait_restore_limits(robz):
    previous_robz = robz.limits
    with cleanup.cleanup(robz, restore_list=(cleanup.axis.LIM,)):
        robz.limits = 1.2, 2.534
    assert robz.limits == previous_robz


def test_motor_wait_restore_position(robz, roby):
    previous_robz = robz.position
    previous_roby = roby.position

    with cleanup.cleanup(robz, roby, restore_list=(cleanup.axis.POS,)):
        robz.rmove(1.242, wait=False)
        roby.rmove(.242, wait=False)
    assert robz.position == previous_robz
    assert roby.position == previous_roby


def test_stoppable_device():
    class Simple:
        def __init__(self):
            self.stop_called = False

        def stop(self):
            self.stop_called = True

    class Cpl:
        def __init__(self):
            self.stop_called = False
            self.stop_acq_called = False

        def stop(self):
            self.stop_called = True

        def stop_blabla(self):
            pass

        def stop_acq(self):
            self.stop_acq_called = True

    s = Simple()
    c = Cpl()
    with cleanup.cleanup(s, c):
        pass
    assert s.stop_called
    assert not c.stop_called
    assert c.stop_acq_called


def test_functions_call():
    test_flags = {"test1_called": 0, "test2_called": 0}

    def test1(**keys):
        keys["flags"]["test1_called"] += 1

    def test2(**keys):
        keys["falgs"]["test2_called"] += 1

    with pytest.raises(KeyError):
        with cleanup.cleanup(test1, test2, test1, flags=test_flags):
            pass

    assert test_flags["test1_called"] == 2
    assert not test_flags["test2_called"]


def test_exceptions_capture(capsys):
    m = mock.Mock()
    with capture_exceptions() as capture:
        with capture():
            m()
    m.assert_called_once_with()

    m = mock.Mock()
    with pytest.raises(ZeroDivisionError) as exc:
        with capture_exceptions() as capture:
            with capture():
                1 / 0
            with capture():
                m()
    m.assert_called_once_with()
    assert len(exc.value.exception_infos) == 1
    assert len(capture.exception_infos) == 1

    m = mock.Mock()
    with pytest.raises(ZeroDivisionError) as exc:
        with capture_exceptions() as capture:
            with capture():
                m()
            1 / 0
    m.assert_called_once_with()
    assert len(exc.value.exception_infos) == 1
    assert len(capture.exception_infos) == 1

    m = mock.Mock()
    with pytest.raises(ZeroDivisionError) as exc:
        with capture_exceptions() as capture:
            with capture():
                raise RuntimeError
            with capture():
                raise ZeroDivisionError
            out, err = capsys.readouterr()
            assert "RuntimeError" in err
            assert out == ""
            with capture():
                m()
    m.assert_called_once_with()
    assert len(exc.value.exception_infos) == 2
    assert len(capture.exception_infos) == 2

    m = mock.Mock()
    with pytest.raises(RuntimeError) as exc:
        with capture_exceptions(raise_index=0) as capture:
            with capture():
                raise RuntimeError
            with capture():
                raise ZeroDivisionError
            out, err = capsys.readouterr()
            assert "ZeroDivisionError" in err
            assert out == ""
            with capture():
                m()
    m.assert_called_once_with()
    assert len(exc.value.exception_infos) == 2
    assert len(capture.exception_infos) == 2

    m = mock.Mock()
    with capture_exceptions(raise_index=None) as capture:
        with capture():
            raise RuntimeError
        out, err = capsys.readouterr()
        assert "RuntimeError" in err
        assert out == ""
        with capture():
            raise ZeroDivisionError
        out, err = capsys.readouterr()
        assert "ZeroDivisionError" in err
        assert out == ""
        with capture():
            m()
    m.assert_called_once_with()
    assert len(capture.exception_infos) == 2
