import os
import signal
import psutil
import gevent
import pytest
from bliss.common import plot
from bliss.scanning.scan_display import ScanDisplay


@pytest.fixture
def watchdog_configuration(session):
    """Fixture to setup ScanDisplay before calling fixture spawning Flint"""
    scan_display = ScanDisplay()
    old_config = scan_display.extra_args
    scan_display.extra_args = ["--enable-watchdog"]
    # bliss.set_bliss_shell_mode(True)
    try:
        yield
    finally:
        scan_display.extra_args = old_config


def kill_flint(pid):
    os.kill(pid, signal.SIGKILL)
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        # process already closed
        pass
    else:
        try:
            psutil.wait_procs([p], timeout=4.0)
        except Exception:
            assert False, "Flint was not closed as expected"


def test_mem_monitoring_when_flint_is_freezed(
    watchdog_configuration, test_session_with_flint, log_directory
):
    """
    Start flint with watchdogs enabled and make it freezed.

    Trigger monitoring using interruption

    Expect monitoring data in the log file
    """
    session = test_session_with_flint
    flint = plot.get_flint()

    def freeze_flint():
        flint.test_infinit_loop()
        assert False, "It is not supposed to return"

    # g = gevent.spawn(freeze_flint)
    # gevent.sleep(5)
    # g.kill()

    pid = flint.pid
    assert psutil.pid_exists(pid)
    process = psutil.Process(pid)

    # Start monitoring
    gevent.sleep(1)
    process.send_signal(signal.SIGUSR1)
    gevent.sleep(1)

    # Log monitoring
    assert psutil.pid_exists(pid)
    process.send_signal(signal.SIGUSR1)
    gevent.sleep(5)

    with open(
        os.path.join(log_directory, f"flint_{session.name}.log"), "rt"
    ) as logfile:
        blob = logfile.read()
        assert "---------- tracemalloc ----------" in blob

    # Close Flint manually cause it could have a weird state
    kill_flint(pid)


def test_stack_monitoring_when_flint_is_freezed(
    watchdog_configuration, test_session_with_flint, log_directory
):
    """
    Start flint with watchdogs enabled and make it freezed.

    Trigger monitoring using interruption

    Expect monitoring data in the log file
    """
    session = test_session_with_flint
    flint = plot.get_flint()

    def freeze_flint():
        flint.test_infinit_loop()
        assert False, "It is not supposed to return"

    # g = gevent.spawn(freeze_flint)
    # gevent.sleep(5)
    # g.kill()

    pid = flint.pid
    assert psutil.pid_exists(pid)
    process = psutil.Process(pid)

    # Request stack state
    gevent.sleep(1)
    process.send_signal(signal.SIGUSR2)
    gevent.sleep(1)

    assert psutil.pid_exists(pid)

    with open(
        os.path.join(log_directory, f"flint_{session.name}.log"), "rt"
    ) as logfile:
        blob = logfile.read()
        assert "---------- tracemalloc ----------" in blob
        assert "---------- greenlet traceback ----------" in blob

    # Close Flint manually cause it could have a weird state
    kill_flint(pid)
