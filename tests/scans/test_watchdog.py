import pytest
import gevent
from bliss.common import scans
from bliss.scanning import scan


def test_watchdog_timeout_normal_stop(session):
    s = scans.timescan(2, run=False)

    class Watchdog(scan.WatchdogCallback):
        def __init__(self):
            super().__init__(0.01)

        def on_timeout(self):
            raise StopIteration

    s.set_watchdog_callback(Watchdog())

    with gevent.Timeout(1):
        s.run()


def test_watchdog_timeout_with_exception(session):
    s = scans.timescan(0.1, run=False)

    class Watchdog(scan.WatchdogCallback):
        def __init__(self):
            super().__init__(0.01)

        def on_timeout(self):
            raise RuntimeError("Bla")

    s.set_watchdog_callback(Watchdog())

    with pytest.raises(RuntimeError):
        with gevent.Timeout(1):
            s.run()


def test_watchdog_timeout_with_baseexception(session):
    s = scans.timescan(0.1, run=False)

    class Watchdog(scan.WatchdogCallback):
        def __init__(self):
            super().__init__(0.01)

        def on_timeout(self):
            # BaseException wich is not Timeout (due to the Timeout in the test)
            # and not KeyboardInterrupt which behave strangely
            # with gevent
            raise GeneratorExit

    s.set_watchdog_callback(Watchdog())

    with gevent.Timeout(1):
        with pytest.raises(GeneratorExit):
            s.run()


def test_watchdog_on_scan_data_normal_stop(session):
    s = scans.timescan(0.1, run=False)

    class Watchdog(scan.WatchdogCallback):
        def __init__(self):
            super().__init__()

        def on_timeout(self):
            raise RuntimeError("Should not be called")

        def on_scan_data(self, data_events, nodes, scan_info):
            raise StopIteration

    s.set_watchdog_callback(Watchdog())

    with gevent.Timeout(1):
        s.run()


def test_watchdog_on_scan_data_with_exception(session):
    s = scans.timescan(0.1, run=False)

    class Watchdog(scan.WatchdogCallback):
        def __init__(self):
            super().__init__()

        def on_timeout(self):
            raise RuntimeError("Should not be called")

        def on_scan_data(self, data_events, nodes, scan_info):
            raise ValueError("Bang!!!")

    s.set_watchdog_callback(Watchdog())

    with pytest.raises(ValueError):
        with gevent.Timeout(1):
            s.run()
