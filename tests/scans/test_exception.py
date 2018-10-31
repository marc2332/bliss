import gevent
from bliss.common import scans
from bliss.common.measurement import SamplingCounter


import pytest


def test_exception_in_reading(beacon):
    event = gevent.event.Event()

    class Cnt(SamplingCounter):
        def __init__(self, npoints):
            SamplingCounter.__init__(self, "bla", None)
            self.nbpoints = npoints

        def read(self):
            try:
                if self.nbpoints > 5:
                    return 1.

                event.set()
                raise RuntimeError("Bla bla bla")
            finally:
                self.nbpoints -= 1

    c = Cnt(10)

    try:
        with gevent.Timeout(1):
            scans.timescan(0, c, npoints=10, save=False)
    except RuntimeError:
        if not event.is_set():
            raise
    except gevent.Timeout:
        assert False


def test_exception_in_first_reading(beacon, bad_diode):
    with pytest.raises(RuntimeError):
        with gevent.Timeout(1):
            scans.timescan(0, bad_diode, npoints=10, save=False)
