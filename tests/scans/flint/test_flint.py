"""Testing Flint."""

import pytest
from bliss.common import plot
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain, AcquisitionChannel, AcquisitionMaster
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
import gevent


def test_empty_plot(flint_session):
    p = plot.plot()
    pid = plot.get_flint()._pid
    assert "flint_pid={}".format(pid) in repr(p)
    assert p.name == "Plot {}".format(p._plot_id)

    p = plot.plot(name="Some name")
    assert "flint_pid={}".format(pid) in repr(p)
    assert p.name == "Some name"


def test_simple_plot(flint_session):
    sin = flint_session.env_dict["sin_data"]
    p = plot.plot(sin)
    assert "CurvePlot" in repr(p)
    data = p.get_data()
    assert data == {
        "default": pytest.approx(sin),
        "x": pytest.approx(list(range(len(sin)))),
    }


def test_plot_curve_with_x(flint_session):
    sin = flint_session.env_dict["sin_data"]
    cos = flint_session.env_dict["cos_data"]
    p = plot.plot({"sin": sin, "cos": cos}, x="sin")
    assert "CurvePlot" in repr(p)
    data = p.get_data()
    assert data == {"sin": pytest.approx(sin), "cos": pytest.approx(cos)}


def test_image_plot(flint_session):
    grey_image = flint_session.env_dict["grey_image"]
    p = plot.plot(grey_image)
    assert "ImagePlot" in repr(p)
    data = p.get_data()
    assert data == {"default": pytest.approx(grey_image)}
    colored_image = flint_session.env_dict["colored_image"]
    p = plot.plot(colored_image)
    assert "ImagePlot" in repr(p)
    data = p.get_data()
    assert data == {"default": pytest.approx(colored_image)}


def test_curve_plot(flint_session):
    dct = flint_session.env_dict["sin_cos_dict"]
    struct = flint_session.env_dict["sin_cos_struct"]
    scan = flint_session.env_dict["sin_cos_scan"]
    for sin_cos in (dct, struct, scan):
        p = plot.plot(sin_cos)
        assert "CurvePlot" in repr(p)
        data = p.get_data()
        assert data == {
            "x": pytest.approx(sin_cos["x"]),
            "sin": pytest.approx(sin_cos["sin"]),
            "cos": pytest.approx(sin_cos["cos"]),
        }


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
