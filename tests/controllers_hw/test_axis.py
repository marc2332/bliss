"""Axis motor hardware tests.

Run with:

    $ pytest --axis-name <axis-name>

"""
import pytest
import time
import gevent


@pytest.fixture
def axis(request, beacon_beamline):
    axis_name = request.config.getoption("--axis-name")
    axis = beacon_beamline.get(axis_name)
    try:
        yield axis
    finally:
        axis.close()


def test_hw_axis_init(axis):
    axis.controller._initialize_axis(axis)


def test_hw_axis_move(axis):
    start_position = axis.position()
    axis.move(start_position + 1.0)
    end_position = axis.position()
    try:
        assert start_position + 1.0 == pytest.approx(end_position, 0.01)
    finally:
        axis.move(start_position)


def test_hw_axis_velocity(axis):
    start_position = axis.position()
    start_velocity = axis.velocity()
    delta_pos = 1.0 + 2.0 * axis.acceleration() * axis.acctime() ** 2
    try:
        start_time = time.time()
        axis.move(start_position + delta_pos)
        end_time = time.time()
        move_time = end_time - start_time

        axis.move(start_position)

        test_velocity = start_velocity / 2.0
        axis.velocity(test_velocity)
        assert pytest.approx(axis.velocity(), test_velocity)
        start_time = time.time()
        axis.move(start_position + delta_pos)
        end_time = time.time()
        move_time_half_speed = end_time - start_time
        assert move_time < move_time_half_speed
    finally:
        axis.velocity(start_velocity)
        axis.move(start_position)


def test_hw_axis_acceleration_set_read(axis):
    start_acceleration = axis.acceleration()
    try:
        axis.acceleration(start_acceleration / 2)
        assert start_acceleration / 2 == pytest.approx(
            axis.acceleration(), start_acceleration / 100.0
        )
    finally:
        axis.acceleration(start_acceleration)


def test_hw_axis_stop(axis):
    start_position = axis.position()
    delta_pos = 1.0 + 2.0 * axis.acceleration() * axis.acctime() ** 2
    delta_time = 2.0 * axis.acctime() + 1.0 / axis.velocity()
    try:
        axis.move(start_position + delta_pos, wait=False)
        gevent.sleep(axis.acctime())
        gevent.sleep(delta_time / 2.0)
        axis.stop()
        assert axis.position() < start_position + delta_pos
    finally:
        axis.move(start_position)
