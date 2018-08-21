import os
import signal
from random import randint
from contextlib import contextmanager
from distutils.spawn import find_executable

import pytest

from bliss.common import plot
from bliss.common import subprocess


@pytest.fixture(scope="session")
def xvfb():
    xvfb = find_executable("Xvfb")
    # Xvfb not found
    if xvfb is None:
        yield
        return
    # Control DISPLAY variable
    try:
        display = os.environ.get("DISPLAY")
        new_display = ":{}".format(randint(100, 1000000000))
        os.environ["DISPLAY"] = new_display
        # Control xvbf process
        try:
            p = subprocess.Popen([xvfb, new_display])
            yield p.pid
        # Teardown process
        finally:
            p.kill()
            p.wait(1.)
    # Restore DISPLAY variable
    finally:
        if display:
            os.environ["DISPLAY"] = display


@contextmanager
def flint_context():
    flint = plot.get_flint()
    yield flint._pid
    plot.reset_flint()
    os.kill(flint._pid, signal.SIGTERM)
    try:
        os.waitpid(flint._pid, 0)
    # It happens sometimes, for some reason
    except OSError:
        pass


@pytest.fixture
def test_session_with_flint(beacon, xvfb, session):
    with flint_context():
        yield session


@pytest.fixture
def flint_session(beacon, xvfb):
    session = beacon.get("flint")
    session.setup()
    try:
        with flint_context():
            yield session
    finally:
        pass
    session.close()
