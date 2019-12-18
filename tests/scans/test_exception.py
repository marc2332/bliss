import gevent
import pytest

from bliss.common import scans
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController


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

    try:
        with gevent.Timeout(1):
            scans.timescan(0, c, npoints=10, save=False)
    except RuntimeError:
        if not event.is_set():
            raise
    except gevent.Timeout:
        assert False


def test_exception_in_first_reading(session, bad_diode):
    with pytest.raises(RuntimeError):
        with gevent.Timeout(1):
            scans.timescan(0, bad_diode, npoints=10, save=False)


def test_restarted_scan(session):
    diode = session.config.get("diode")
    s = scans.loopscan(1, 0, diode, save=False, run=False)
    s.run()
    with pytest.raises(RuntimeError):
        s.run()
