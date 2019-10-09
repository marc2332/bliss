import pytest
import gevent
import numpy
from bliss.common import plot
from bliss.common.plot import get_flint
from bliss.common.scans import plotselect
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain, AcquisitionChannel, AcquisitionMaster
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster


def test_get_plot(test_session_with_flint, lima_simulator):
    session = test_session_with_flint
    lima = session.config.get("lima_simulator")
    simu1 = session.config.get("simu1")
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    flint = get_flint()

    plotselect(diode)

    # s = ascan(roby, 0, 5, 5, 0.001, diode, lima, simu1.counters.spectrum_det0)
    s = ascan(roby, 0, 5, 5, 0.001, diode, lima)

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
    assert len(p1_data["axis:roby"]) == 6  # 5 intervals
    for k, v in p1_data.items():
        assert numpy.allclose(p2_data[k], v)

    # p3 = s.get_plot(simu1.counters.spectrum_det0, wait=True)
    # p4 = s.get_plot(simu1, wait=True)
    #
    # assert p3.plot_id == p4.plot_id
    # assert p3.get_data()["simu1:spectrum_det0"].shape[0] == 1024

    p5 = s.get_plot(lima)
    assert len(p5.get_data()["lima_simulator:image"].shape) == 2


def test_image_display(flint_session, lima_simulator, dummy_acq_device):
    chain = AcquisitionChain()
    lima_sim = flint_session.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    lima_master.add_counter(lima_sim.counters.image)
    device = dummy_acq_device.get(None, "dummy", npoints=1)
    chain.add(lima_master, device)
    scan = Scan(chain, "test")
    scan.run()
    p = scan.get_plot(lima_sim, wait=True)
    assert isinstance(p, plot.ImagePlot)
