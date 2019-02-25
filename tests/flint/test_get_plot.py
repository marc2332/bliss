"""Testing Flint."""

import pytest
import gevent
import numpy
from bliss.common.plot import get_flint
from bliss.common.scans import plotselect


def test_get_plot(beacon, lima_simulator, test_session_with_flint):
    lima = beacon.get("lima_simulator")
    simu1 = beacon.get("simu1")
    flint = get_flint()

    ascan = test_session_with_flint.env_dict["ascan"]
    roby = test_session_with_flint.env_dict["roby"]
    diode = test_session_with_flint.env_dict["diode"]
    plotselect(diode)

    s = ascan(roby, 0, 5, 5, 0.001, diode, lima, simu1.counters.spectrum_det0)

    # synchronize redis events with flint
    flint.wait_end_of_scan()

    with gevent.Timeout(30.):
        p1 = s.get_plot(roby, wait=True)
    with pytest.raises(TypeError):
        # plot curves cannot be pickled, so we expect
        # an exception here -- this is to check there
        # is at least one plot
        x = p1.submit("__getattribute__", "_curves")

    p2 = s.get_plot(diode)

    assert p1.plot_id == p2.plot_id
    p1_data = p1.get_data()
    p2_data = p2.get_data()
    assert len(p1_data["axis:roby"]) == 5
    for k, v in p1_data.items():
        assert numpy.allclose(p2_data[k], v)

    p3 = s.get_plot(simu1.counters.spectrum_det0, wait=True)
    p4 = s.get_plot(simu1, wait=True)

    assert p3.plot_id == p4.plot_id
    assert p3.get_data()["simu1:spectrum_det0"].shape[0] == 1024

    p5 = s.get_plot(lima)
    assert len(p5.get_data()["lima_simulator:image"].shape) == 2
