import gevent
import pytest

from bliss.common import scans
from bliss.common.counter import SamplingCounter
from bliss.controllers.counter import SamplingCounterController
from bliss.common.soft_axis import SoftAxis
from bliss.scanning.scan import ScanState, Scan, ScanPreset, ScanAbort
from bliss.scanning.chain import AcquisitionMaster, AcquisitionChain
from bliss.scanning.group import Sequence


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

    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED


def test_exception_in_first_reading(session, bad_diode):
    s = scans.timescan(0, bad_diode, npoints=10, save=False, run=False)
    with pytest.raises(RuntimeError):
        with gevent.Timeout(1):
            s.run()

    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED


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

    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED


def test_exception_on_kill(default_session):
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")
    s = scans.ascan(roby, 0, 1, 100, .1, diode, save=False, run=False)

    g = gevent.spawn(s.run)
    gevent.sleep(.5)
    g.kill()

    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED


def test_exception_on_KeyboardInterrupt(default_session):
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")
    s = scans.ascan(roby, 0, 1, 100, .1, diode, save=False, run=False)

    scan_task = gevent.spawn(s.run)
    gevent.sleep(0.5)
    with pytest.raises(ScanAbort):
        scan_task.kill(KeyboardInterrupt)
        scan_task.get()

    assert s.state == ScanState.USER_ABORTED
    assert s.node.info["state"] == ScanState.USER_ABORTED


def test_exception_in_preset(default_session):
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")

    class Preset1(ScanPreset):
        def stop(self, scan):
            raise BufferError()

    s = scans.ascan(roby, 0, 1, 3, .1, diode, save=False, run=False)
    p = Preset1()
    s.add_preset(p)
    scan_task = gevent.spawn(s.run)
    scan_task.join()
    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED

    class Preset2(ScanPreset):
        def start(self, scan):
            raise BufferError()

    s = scans.ascan(roby, 0, 1, 3, .1, diode, save=False, run=False)
    p = Preset2()
    s.add_preset(p)
    scan_task = gevent.spawn(s.run)
    scan_task.join()
    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED

    class Preset3(ScanPreset):
        def prepare(self, scan):
            raise BufferError()

    s = scans.ascan(roby, 0, 1, 3, .1, diode, save=False, run=False)
    p = Preset3()
    s.add_preset(p)
    scan_task = gevent.spawn(s.run)
    scan_task.join()
    assert s.state == ScanState.KILLED
    assert s.node.info["state"] == ScanState.KILLED


def test_sequence_state(default_session):
    diode = default_session.config.get("diode")
    roby = default_session.config.get("roby")

    seq = Sequence()

    def task():
        class Preset1(ScanPreset):
            def stop(self, scan):
                raise BufferError()

        with seq.sequence_context() as scan_seq:
            s1 = scans.ascan(roby, 0, 1, 3, .1, diode, save=False, run=False)
            scan_seq.add_and_run(s1)
            s = scans.ascan(roby, 0, 1, 3, .1, diode, save=False, run=False)
            p = Preset1()
            s.add_preset(p)
            scan_seq.add_and_run(s)

    scan_task = gevent.spawn(task)
    scan_task.join()

    assert seq.scan.state == ScanState.KILLED
    assert seq.scan.node.info["state"] == ScanState.KILLED


@pytest.mark.parametrize(
    "first_iteration,preset",
    [(True, False), (False, False), (True, True), (False, True)],
)
def test_exception_in_start_and_stop_and_preset(session, first_iteration, preset):
    class Master(AcquisitionMaster):
        name = "bla"

        def __iter__(self):
            self.it = 0
            for i in range(3):
                yield self
                self.it += 1

        def prepare(self):
            pass

        def start(self):
            if first_iteration or self.it > 1:
                1 / 0

        def stop(self):
            raise RuntimeError()

    class Preset(ScanPreset):
        def stop(self, scan):
            raise BufferError()

    m = Master()
    c = AcquisitionChain()
    c.add(m)
    s = Scan(c)
    if preset:
        p = Preset()
        s.add_preset(p)
    try:
        with gevent.Timeout(1):
            s.run()
    except Exception as e:
        assert isinstance(e, ZeroDivisionError)
    else:
        assert False
