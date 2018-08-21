"""Testing Flint."""

import numpy


def test_get_plot(beacon, lima_simulator, test_session_with_flint):
    lima = beacon.get("lima_simulator")
    simu1 = beacon.get("simu1")

    ascan = test_session_with_flint.env_dict["ascan"]
    roby = test_session_with_flint.env_dict["roby"]
    diode = test_session_with_flint.env_dict["diode"]

    s = ascan(roby, 0, 5, 5, 0.001, diode, lima, simu1.counters.spectrum_det0)

    p1 = s.get_plot(roby)
    p2 = s.get_plot(diode)

    assert p1.plot_id == p2.plot_id
    p2_data = p2.get_data()
    for k, v in p1.get_data().iteritems():
        assert numpy.allclose(p2_data[k], v)

    p3 = s.get_plot(simu1.counters.spectrum_det0, wait=True)
    p4 = s.get_plot(simu1, wait=True)

    assert p3.plot_id == p4.plot_id
    assert p3.get_data()["simu1:spectrum_det0"].shape[0] == 1024

    p5 = s.get_plot(lima)
    assert len(p5.get_data()["lima_simulator:image"].shape) == 2
