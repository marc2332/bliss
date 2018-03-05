"""Testing Flint."""

import os
import subprocess
from distutils.spawn import find_executable

import pytest

from bliss.common import plot


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
        os.environ['DISPLAY'] = ':99'
        # Control xvbf process
        try:
            p = subprocess.Popen([xvfb, ':99'], close_fds=True)
            yield p.pid
        # Teardown process
        finally:
            p.kill()
            p.wait(1.)
    # Restore DISPLAY variable
    finally:
        if display:
            os.environ['DISPLAY'] = display


@pytest.fixture(scope='session')
def flint(xvfb, beacon):
    try:
        flint_pid = plot.get_flint_process()
        yield flint_pid
    finally:
        plot.FLINT_PROCESS.kill()
        plot.FLINT_PROCESS.wait(1.)


def test_empty_plot(flint):
    p = plot.plot(name='Some name')
    assert 'flint_pid={}'.format(flint) in repr(p)
    assert p.qt.windowTitle() == 'Some name'
