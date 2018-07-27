import os
import signal
from random import randint
from distutils.spawn import find_executable

import pytest

from bliss.common import plot
from bliss.common import subprocess


@pytest.fixture(scope='session')
def xvfb():
    xvfb = find_executable('Xvfb')
    # Xvfb not found
    if xvfb is None:
        yield
        return
    # Control DISPLAY variable
    try:
        display = os.environ.get('DISPLAY')
        new_display = ':{}'.format(randint(100, 1000000000))
        os.environ['DISPLAY'] = new_display
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
            os.environ['DISPLAY'] = display


@pytest.fixture
def flint(xvfb, beacon, session):
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
def flint_session(beacon, flint):
    env_dict = dict()
    session = beacon.get("flint")
    session.setup(env_dict)
    try:
        yield env_dict
    finally:
        pass
    session.close()
