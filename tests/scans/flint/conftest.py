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
            p = subprocess.Popen([xvfb, "-screen", "0", "1024x768x24", new_display])
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
    pid = flint._pid
    yield pid
    plot.reset_flint()
    os.kill(pid, signal.SIGTERM)
    try:
        os.waitpid(pid, 0)
    # It happens sometimes, for some reason
    except OSError:
        pass


@pytest.fixture
def test_session_with_flint(xvfb, beacon, session):
    with flint_context():
        yield session


@pytest.fixture
def flint_session(xvfb, beacon):
    session = beacon.get("flint")
    session.setup()
    with flint_context():
        yield session
    session.close()
