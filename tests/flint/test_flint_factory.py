"""Testing Flint creating."""

import time
import os
import signal
import pytest
from contextlib import contextmanager

from silx.utils import testutils
from bliss.common import plot


@contextmanager
def attached_flint_context():
    """
    Create and release a flint process.

    The process is still created but re-attached, in order to test using psutil.
    """
    flint = plot.get_flint()
    pid = flint._pid
    flint = plot.attach_flint(pid)
    yield pid
    flint = None  # Break the reference to the proxy
    plot.reset_flint()
    os.kill(pid, signal.SIGTERM)
    try:
        os.waitpid(pid, 0)
    except OSError:
        # It happens sometimes, for some reason
        pass


@pytest.fixture
def attached_flint_session(xvfb, beacon):
    session = beacon.get("flint")
    session.setup()
    with attached_flint_context():
        yield session
    session.close()


def test_created_flint(flint_session):
    """
    Flint is created and attached with subprocess
    """
    flint = plot.get_flint()
    flint.wait_started()
    # Check messages and stdout
    listener = testutils.TestLogging(plot.FLINT_OUTPUT_LOGGER.name, info=1)
    with listener:
        flint.ping()
        for _ in range(10):
            if len(listener.records) >= 1:
                # Early break
                break
            time.sleep(0.5)


def test_attached_flint(attached_flint_session):
    """
    Flint is already created and attached with psutil/stream
    """
    flint = plot.get_flint()
    # Check messages and stdout
    listener = testutils.TestLogging(plot.FLINT_OUTPUT_LOGGER.name, info=1)
    with listener:
        flint.ping()
        for _ in range(10):
            if len(listener.records) >= 1:
                # Early break
                break
            time.sleep(0.5)
