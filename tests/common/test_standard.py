
import pytest
import gevent

from bliss.shell.standard import lscnt, bench, lsobj

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
EXPECTED_DIODE_ONLY = """
Fullname                                    Shape    Controller                            Name    Alias
------------------------------------------  -------  ------------------------------------  ------  -------
simulation_diode_sampling_controller:diode  0D       simulation_diode_sampling_controller  diode
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

    diode = beacon.get("diode")
    lscnt(diode)
    captured = capsys.readouterr()
    assert captured.out == EXPECTED_DIODE_ONLY


def test_bench(beacon, setup_globals, capsys):
    with bench():
        gevent.sleep(1)

    captured = capsys.readouterr()
    assert "Execution time: 1s" in captured.out


def test_lsobj(session, beacon, setup_globals, capsys):
    """ Test 'lsobj' function to list objects in a session.
    """

    # should return all objects of the session
    lsobj()
    captured = capsys.readouterr()
    s1 = (
        f"beamstop  att1  MG1  MG2  bad  calc_mot1  calc_mot2  custom_axis  diode  "
        "diode2  diode3  diode4  diode5  diode6  diode7  diode8  diode9  heater  "
        "hook0  hook1  hooked_error_m0  hooked_m0  hooked_m1  integ_diode  jogger  "
        "m0  m1  m1enc  omega  roby  robz  robz2  s1b  s1d  s1f  s1hg  s1ho  s1u  "
        "s1vg  s1vo  sample_regulation  sample_regulation_new  sensor  sim_ct_gauss  "
        "sim_ct_gauss_noise  sim_ct_flat_12  sim_ct_rand_12  test  test_mg  "
        "thermo_sample  transfocator_simulator  \n"
    )

    assert s1 == captured.out

    # test with '*' jocker character.
    lsobj("dio*")
    captured = capsys.readouterr()
    assert "diode  diode2  diode3  diode4  diode5  diode6" in captured.out
