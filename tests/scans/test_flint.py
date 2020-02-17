import gevent
import numpy
import contextlib

import bliss
from bliss.common import plot
from bliss.common.plot import get_flint
from bliss.common.scans import plotselect
from bliss.common.scans import meshselect
from bliss.scanning.scan import Scan, ScanDisplay
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster


def test_get_plot(test_session_with_flint, lima_simulator):
    session = test_session_with_flint
    lima = session.config.get("lima_simulator")
    # simu1 = session.config.get("simu1")
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    flint = get_flint()

    plotselect(diode)

    # s = ascan(roby, 0, 5, 5, 0.001, diode, lima, simu1.counters.spectrum_det0)
    ascan(roby, 0, 5, 5, 0.001, diode, lima)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    p1_data = flint.get_live_scan_data("axis:roby")
    p2_data = flint.get_live_scan_data(diode.fullname)

    assert len(p1_data) == 6  # 5 intervals
    assert len(p2_data) == 6  # 5 intervals
    assert numpy.allclose(p1_data, numpy.arange(6))

    # p3 = s.get_plot(simu1.counters.spectrum_det0, wait=True)
    # p4 = s.get_plot(simu1, wait=True)
    #
    # assert p3.plot_id == p4.plot_id
    # assert p3.get_data()["simu1:spectrum_det0"].shape[0] == 1024

    p5_data = flint.get_live_scan_data(lima.image.fullname)
    assert len(p5_data.shape) == 2


def test_image_display(flint_session, lima_simulator, dummy_acq_device):
    chain = AcquisitionChain()
    lima_sim = flint_session.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    lima_master.add_counter(lima_sim.counters.image)
    device = dummy_acq_device.get(None, name="dummy", npoints=1)
    chain.add(lima_master, device)
    scan = Scan(chain, "test")
    scan.run()
    p = scan.get_plot(lima_sim.image, plot_type="image", wait=True)
    assert isinstance(p, plot.ImagePlot)


@contextlib.contextmanager
def use_shell_command_with_flint():
    scan_display = ScanDisplay()
    old_auto = scan_display.auto
    old_motor_position = scan_display.motor_position
    old_shell = bliss.is_bliss_shell()
    bliss.set_bliss_shell_mode(True)
    scan_display.auto = True
    scan_display.motor_position = True
    try:
        yield
    finally:
        bliss.set_bliss_shell_mode(old_shell)
        scan_display.auto = old_auto
        scan_display.motor_position = old_motor_position


def test_motor_position_in_plot(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    flint = get_flint()
    import logging

    l = logging.getLogger("flint.output")
    l.disabled = False
    l.setLevel(logging.INFO)

    plotselect(diode)
    scan = ascan(roby, 0, 5, 5, 0.001, diode)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    # display the motor destination to flint
    with use_shell_command_with_flint():
        scan.goto_cen(diode)
    gevent.sleep(1)


def test_meshselect(test_session_with_flint):
    session = test_session_with_flint
    amesh = session.env_dict["amesh"]
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
    diode3 = session.config.get("diode3")
    flint = get_flint()
    import logging

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    _scan = amesh(roby, 0, 5, 2, robz, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    plot_id = flint.get_default_live_scan_plot("scatter")

    # Select the second diode
    meshselect(diode2)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(plot_id) == 1

    # Select a diode which was not scanned
    meshselect(diode3)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(plot_id) == 0


def test_plotselect(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
    diode3 = session.config.get("diode3")
    flint = get_flint()
    import logging

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    _scan = ascan(roby, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    plot_id = flint.get_default_live_scan_plot("curve")

    # Select the second diode
    plotselect(diode2)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(plot_id) == 1

    # Select a diode which was not scanned
    plotselect(diode3)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(plot_id) == 0
