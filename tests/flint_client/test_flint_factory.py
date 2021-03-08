"""Testing Flint creating."""

import time
import os
import signal
import pytest
import gevent
import psutil
from contextlib import contextmanager

from silx.utils import testutils
from bliss.common import plot
from bliss.flint.client import proxy


class ExtTestLogging(testutils.TestLogging):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            testutils.TestLogging.__exit__(self, exc_type, exc_value, traceback)
        except RuntimeError:
            # In case of problem, display the received logs
            for r in self.records:
                print(r.levelname, r.name, self.format(r))
            raise


@contextmanager
def attached_flint_context():
    """
    Create and release a flint process.

    The process is still created but re-attached, in order to test using psutil.
    """
    flint = plot.get_flint()
    pid = flint._pid
    flint._proxy_cleanup()
    # Release the object before calling attach_flint
    flint = None
    flint = plot.attach_flint(pid)
    yield pid
    flint = None  # Break the reference to the proxy
    plot.close_flint()


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
    flint = plot.get_flint(creation_allowed=False)

    # Check messages and stdout
    listener = ExtTestLogging(proxy.FLINT_OUTPUT_LOGGER.name, info=1)
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
    listener = ExtTestLogging(proxy.FLINT_OUTPUT_LOGGER.name, info=1)
    with listener:
        flint.ping()
        for _ in range(10):
            # wait until and answer
            time.sleep(0.5)
            if len(listener.records) >= 1:
                # Early break
                break


def test_restart_flint(flint_session):
    """
    Test that the restart API is working in normal condition
    """
    flint = plot.get_flint()
    previous_pid = flint._pid

    try:
        flint = plot.restart_flint()
        assert previous_pid != flint._pid
    finally:
        flint.kill9()


def test_restart_unresponsive_flint(flint_session):
    """
    Test that the restart API is working despite unresponsive Flint
    """
    flint = plot.get_flint()
    previous_pid = flint._pid

    def freeze_flint():
        flint.test_infinit_loop()
        assert False, "It is not supposed to return"

    g = gevent.spawn(freeze_flint)
    gevent.sleep(0.5)
    g.kill()

    try:
        flint = plot.restart_flint()
        assert not psutil.pid_exists(previous_pid)
        assert flint is not None
    finally:
        flint.kill9()
