import gevent
import pytest

from bliss.common import scans
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.common.soft_axis import SoftAxis


def test_exception_in_reading(session):
    event = gevent.event.Event()

    class CntController(SamplingCounterController):
        def __init__(self):
            super().__init__("cnt_controller")

        def read(self, counter):
            try:
                if counter.nbpoints > 5:
                    return 1.

                event.set()
                gevent.sleep(10e-3)
                raise RuntimeError("Bla bla bla")
            finally:
                counter.nbpoints -= 1

    class Cnt(SamplingCounter):
        def __init__(self, npoints):
            SamplingCounter.__init__(self, "bla", CntController())
            self.nbpoints = npoints

    c = Cnt(10)
    s = scans.timescan(0, c, npoints=10, save=False, run=False)

    try:
        with gevent.Timeout(1):
            s.run()
    except RuntimeError:
        if not event.is_set():
            raise
    except gevent.Timeout:
        assert False

    assert s.state.name == "KILLED"


def test_exception_in_first_reading(session, bad_diode):
    s = scans.timescan(0, bad_diode, npoints=10, save=False, run=False)
    with pytest.raises(RuntimeError):
        with gevent.Timeout(1):
            s.run()

    assert s.state.name == "KILLED"


def test_restarted_scan(session):
    diode = session.config.get("diode")
    s = scans.loopscan(1, 0, diode, save=False, run=False)
    s.run()
    with pytest.raises(RuntimeError):
        s.run()


def test_exception_in_move(default_session):
    class FailingAxis:
        def __init__(self):
            self._position = 0

        @property
        def position(self):
            return self._position

        @position.setter
        def position(self, value):
            if value > 1:
                raise RuntimeError
            self._position = value

    diode = default_session.config.get("diode")
    axis = SoftAxis("TestAxis", FailingAxis())

    s = scans.ascan(axis, 0, 2, 5, .1, diode, save=False, run=False)
    with pytest.raises(RuntimeError):
        s.run()

    assert s.state.name == "KILLED"


def test_exception_on_kill(default_session):
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")
    s = scans.ascan(roby, 0, 1, 100, .1, diode, save=False, run=False)

    g = gevent.spawn(s.run)
    gevent.sleep(.5)
    g.kill()

    assert s.state.name == "KILLED"


def test_exception_on_KeyboardInterrupt(default_session):
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")
    s = scans.ascan(roby, 0, 1, 100, .1, diode, save=False, run=False)

    scan_task = gevent.spawn(s.run)
    gevent.sleep(0.5)
    with pytest.raises(KeyboardInterrupt):
        scan_task.kill(KeyboardInterrupt)

    assert s.state.name == "USER_ABORTED"
