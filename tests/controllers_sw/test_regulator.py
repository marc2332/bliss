import pytest
import time
from bliss.controllers.regulator import send_limit


@send_limit
def test_send_limit():
    return 0


@send_limit
def test_send_limit_bis():
    return 0


def test_command_per_second():
    """Test it's not possible to have more than 10 commands per second"""
    start = time.time()
    for i in range(10):
        test_send_limit()
    end = time.time()
    total = end - start
    assert total >= 1


def test_different_instance():
    """Test if the decorator uses its own _last_call"""
    time.sleep(0.15)
    start = time.time()
    test_send_limit()
    test_send_limit_bis()
    end = time.time()
    total = end - start
    assert total < 0.15
