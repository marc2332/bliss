
import pytest
import gevent

from bliss.shell.standard import lscnt, bench

EXPECTED = """
Fullname             Shape    Controller    Name           Alias
-------------------  -------  ------------  -------------  -------
simu1:deadtime_det0  0D       simu1         deadtime_det0
simu1:deadtime_det1  0D       simu1         deadtime_det1
simu1:deadtime_det2  0D       simu1         deadtime_det2
simu1:deadtime_det3  0D       simu1         deadtime_det3
simu1:events_det0    0D       simu1         events_det0
simu1:events_det1    0D       simu1         events_det1
simu1:events_det2    0D       simu1         events_det2
simu1:events_det3    0D       simu1         events_det3
simu1:icr_det0       0D       simu1         icr_det0
simu1:icr_det1       0D       simu1         icr_det1
simu1:icr_det2       0D       simu1         icr_det2
simu1:icr_det3       0D       simu1         icr_det3
simu1:livetime_det0  0D       simu1         livetime_det0
simu1:livetime_det1  0D       simu1         livetime_det1
simu1:livetime_det2  0D       simu1         livetime_det2
simu1:livetime_det3  0D       simu1         livetime_det3
simu1:ocr_det0       0D       simu1         ocr_det0
simu1:ocr_det1       0D       simu1         ocr_det1
simu1:ocr_det2       0D       simu1         ocr_det2
simu1:ocr_det3       0D       simu1         ocr_det3
simu1:realtime_det0  0D       simu1         realtime_det0
simu1:realtime_det1  0D       simu1         realtime_det1
simu1:realtime_det2  0D       simu1         realtime_det2
simu1:realtime_det3  0D       simu1         realtime_det3
simu1:spectrum_det0  1D       simu1         spectrum_det0
simu1:spectrum_det1  1D       simu1         spectrum_det1
simu1:spectrum_det2  1D       simu1         spectrum_det2
simu1:spectrum_det3  1D       simu1         spectrum_det3
simu1:triggers_det0  0D       simu1         triggers_det0
simu1:triggers_det1  0D       simu1         triggers_det1
simu1:triggers_det2  0D       simu1         triggers_det2
simu1:triggers_det3  0D       simu1         triggers_det3
"""


@pytest.fixture
def setup_globals():
    from bliss import setup_globals

    save = dict(setup_globals.__dict__)
    try:
        setup_globals.__dict__.clear()
        yield setup_globals
    finally:
        setup_globals.__dict__.clear()
        setup_globals.__dict__.update(save)


def test_lscnt(beacon, setup_globals, capsys):
    setup_globals.simu1 = beacon.get("simu1")
    assert lscnt() is None
    captured = capsys.readouterr()
    assert captured.out == EXPECTED


def test_bench(beacon, setup_globals, capsys):
    with bench():
        gevent.sleep(1)

    captured = capsys.readouterr()
    assert "Execution time: 1s" in captured.out
