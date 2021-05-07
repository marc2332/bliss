import pytest
import gevent
import numpy
import contextlib
import logging

import bliss
from bliss.common import plot
from bliss.controllers import simulation_counter
from bliss.flint.client import plots
from bliss.scanning.scan import Scan
from bliss.scanning.scan_info import ScanInfo
from bliss.scanning.scan_display import ScanDisplay
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning.group import Sequence


def test_ascan(test_session_without_flint, lima_simulator):
    """
    Test that a ascan data is displayed in Flint when using SCAN_DISPLAY.auto=True
    """
    session = test_session_without_flint
    lima = session.config.get("lima_simulator")
    # simu1 = session.config.get("simu1")
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")

    with use_shell_mode():
        with use_scan_display(auto=True, motor_position=True):
            ascan(roby, 0, 5, 5, 0.001, diode, lima)

    flint = plot.get_flint()
    flint.wait_end_of_scans()

    p1_data = flint.get_live_scan_data("axis:roby")
    p2_data = flint.get_live_scan_data(diode.fullname)

    assert len(p1_data) == 6  # 5 intervals
    assert len(p2_data) == 6  # 5 intervals
    assert numpy.allclose(p1_data, numpy.arange(6))

    p5_data = flint.get_live_scan_data(lima.image.fullname)
    assert len(p5_data.shape) == 2


def test_custom_mesh_plot(test_session_with_flint):
    session = test_session_with_flint
    # simu1 = session.config.get("simu1")
    amesh = session.env_dict["amesh"]
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
    flint = plot.get_flint()

    s = amesh(roby, 0, 1, 3, robz, 0, 1, 3, 0.001, diode, diode2, run=False)

    # add a custom plot
    s.scan_info.add_scatter_plot(
        name="foo", x="axis:roby", y="axis:robz", value=diode2.fullname
    )
    s.run()

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot("default-scatter")
    p2 = flint.get_live_scan_plot(diode2.fullname, "scatter")

    assert p1 != p2
    assert p2 is not None
    assert flint.get_plot_name(p2) == "foo"


def test_ct_image(test_session_without_flint, lima_simulator):
    """Flint is expected with a ct on an image"""
    session = test_session_without_flint
    lima = session.config.get("lima_simulator")
    ct = session.env_dict["ct"]
    with use_shell_mode():
        with use_scan_display(auto=True, motor_position=True):
            ct(0.1, lima)
    flint = plot.get_flint(creation_allowed=False)
    assert flint is not None


def test_live_plot_image(test_session_without_flint, lima_simulator):
    """Test the API provided by the live image plot"""
    session = test_session_without_flint
    lima = session.config.get("lima_simulator")
    ct = session.env_dict["ct"]
    with use_shell_mode():
        with use_scan_display(auto=True, motor_position=True):
            ct(0.1, lima)
    flint = plot.get_flint(creation_allowed=False)
    assert flint is not None

    p = flint.get_live_plot(image_detector="lima_simulator")
    assert p is not None
    p.set_colormap(lut="viridis")
    p.set_colormap(lut="gray")
    p.set_colormap(vmin=50)
    p.set_colormap(vmin="auto")
    p.set_colormap(vmax=10000)
    p.set_colormap(vmax="auto")
    p.set_colormap(normalization="log")
    p.set_colormap(gamma_normalization=0.5)
    p.set_colormap(normalization="linear")
    with pytest.raises(Exception):
        p.set_colormap(normalization="foo")
    p.set_colormap(autoscale=True)
    p.set_colormap(autoscale_mode="minmax")
    p.set_colormap(autoscale_mode="stddev3")


def test_ct_diode(test_session_without_flint):
    """Flint is not expected with a ct on a diode"""
    session = test_session_without_flint
    ct = session.env_dict["ct"]
    diode = session.config.get("diode")
    with use_shell_mode():
        with use_scan_display(auto=True, motor_position=True):
            ct(0.1, diode)
    flint = plot.get_flint(creation_allowed=False)
    assert flint is None


def test_image_display(flint_session, lima_simulator, dummy_acq_device):
    chain = AcquisitionChain()
    lima_sim = flint_session.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    lima_master.add_counter(lima_sim.counters.image)
    device = dummy_acq_device.get(None, name="dummy", npoints=1)
    chain.add(lima_master, device)
    scan = Scan(chain, "test")
    scan.run()

    # depricated access but kept for compatibilty with older versions...
    p = scan.get_plot(lima_sim.image, plot_type="image", wait=True)
    assert isinstance(p, plots.ImagePlot)

    # new access
    p = plot.get_plot(lima_sim.image, scan=scan, plot_type="image", wait=True)
    assert isinstance(p, plots.ImagePlot)


def test_restart_flint_if_stucked(
    test_session_with_stucked_flint, lima_simulator, dummy_acq_device
):
    chain = AcquisitionChain()
    lima_sim = test_session_with_stucked_flint.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    lima_master.add_counter(lima_sim.counters.image)
    device = dummy_acq_device.get(None, name="dummy", npoints=1)
    chain.add(lima_master, device)
    with use_shell_mode():
        with use_scan_display(auto=True, restart_flint_if_stucked=True):
            scan = Scan(chain, "test")
            scan.run()

    # depricated access but kept for compatibilty with older versions...
    p = scan.get_plot(lima_sim.image, plot_type="image", wait=True)
    assert isinstance(p, plots.ImagePlot)

    # new access
    p = plot.get_plot(lima_sim.image, scan=scan, plot_type="image", wait=True)
    assert isinstance(p, plots.ImagePlot)


def test_ignore_flint_if_stucked(
    test_session_with_stucked_flint, lima_simulator, dummy_acq_device
):
    chain = AcquisitionChain()
    lima_sim = test_session_with_stucked_flint.config.get("lima_simulator")
    lima_master = LimaAcquisitionMaster(lima_sim, acq_nb_frames=1, acq_expo_time=0.1)
    lima_master.add_counter(lima_sim.counters.image)
    device = dummy_acq_device.get(None, name="dummy", npoints=1)
    chain.add(lima_master, device)
    with use_shell_mode():
        with use_scan_display(auto=True, restart_flint_if_stucked=False):
            scan = Scan(chain, "test")
            scan.run()

    assert plot.get_flint(mandatory=False) is None


@contextlib.contextmanager
def active_video_live(lima):
    old = lima.proxy.video_live
    lima.proxy.video_live = True
    try:
        yield
    finally:
        lima.proxy.video_live = old


def test_image_monitoring(test_session_without_flint, lima_simulator):
    """Use the Flint monitoring API to check that an image was retrieved"""
    session = test_session_without_flint
    lima = session.config.get("lima_simulator")
    ct = session.env_dict["ct"]
    channel_name = lima.image.fullname
    tango_address = lima.proxy.name()

    # initialize the device with an image
    ct(0.1, lima)

    with active_video_live(lima):
        # start flint and the monitoring
        with use_shell_mode():
            with use_scan_display(auto=True, motor_position=True):
                flint = plot.get_flint()
                flint.start_image_monitoring(channel_name, tango_address)
                gevent.sleep(2)
                flint.stop_image_monitoring(channel_name)

        # it should display an image
        plot_id = flint.get_live_scan_plot(channel_name, "image")
        nb = flint.test_count_displayed_items(plot_id)

    assert nb == 1


@contextlib.contextmanager
def use_scan_display(auto=None, motor_position=None, restart_flint_if_stucked=None):
    """Setup scan display with a specific value.

    The initial state is restored at the end of the context.
    """
    scan_display = ScanDisplay()
    old_auto = scan_display.auto
    old_motor_position = scan_display.motor_position
    old_restart_flint_if_stucked = scan_display.restart_flint_if_stucked
    if auto is not None:
        scan_display.auto = True
    if motor_position is not None:
        scan_display.motor_position = motor_position
    if restart_flint_if_stucked is not None:
        scan_display.restart_flint_if_stucked = restart_flint_if_stucked
    try:
        yield
    finally:
        if auto is not None:
            scan_display.auto = old_auto
        if motor_position is not None:
            scan_display.motor_position = old_motor_position
        if restart_flint_if_stucked is not None:
            scan_display.restart_flint_if_stucked = old_restart_flint_if_stucked


@contextlib.contextmanager
def use_shell_mode():
    """
    Force the use of the BLISS shell mode.

    The initial state is restored at the end of the context.
    """
    old_shell = bliss.is_bliss_shell()
    bliss.set_bliss_shell_mode(True)
    try:
        yield
    finally:
        bliss.set_bliss_shell_mode(old_shell)


def test_motor_position_in_plot(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    flint = plot.get_flint()

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    plot.plotselect(diode)
    scan = ascan(roby, 0, 5, 5, 0.001, diode)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    # display the motor destination to flint
    with use_shell_mode():
        with use_scan_display(auto=True, motor_position=True):
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
    flint = plot.get_flint()

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    _scan = amesh(roby, 0, 5, 2, robz, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot("default-scatter")

    # Select the second diode
    plot.meshselect(diode2)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(p1.plot_id) == 1

    # Select a diode which was not scanned
    plot.meshselect(diode3)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(p1.plot_id) == 0


def test_plotinit__something(session):
    plot.plotinit("aaa")
    channels = plot.get_next_plotted_counters()
    assert channels == ["aaa"]


def test_plotinit__nothing(session):
    plot.plotinit()
    assert session.scan_display.next_scan_displayed_channels is None
    assert plot.get_next_plotted_counters() == []


def test_plotinit__one_shot(session):
    plot.plotinit("aaa")
    session.scan_display._pop_next_scan_displayed_channels()
    assert plot.get_next_plotted_counters() == []


def test_plotselect(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
    diode3 = session.config.get("diode3")
    flint = plot.get_flint()

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    _scan = ascan(roby, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot("default-curve")

    # Select the second diode
    plot.plotselect(diode2)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(p1.plot_id) == 1

    # Select a diode which was not scanned
    plot.plotselect(diode3)
    gevent.sleep(1)
    assert flint.test_count_displayed_items(p1.plot_id) == 0


def test_plotselect__before_startup(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")

    plot.plotselect(diode2)

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    flint = plot.get_flint()
    ascan(roby, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()
    p1 = flint.get_live_plot("default-curve")
    assert diode2.fullname in flint.test_displayed_channel_names(p1.plot_id)


def test_plotselect__switch_scan(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    loopscan = session.env_dict["loopscan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")

    flint = plot.get_flint()

    plot.plotselect(diode2)

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    ascan(roby, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()
    p1 = flint.get_live_plot("default-curve")
    assert diode2.fullname in flint.test_displayed_channel_names(p1.plot_id)

    loopscan(5, 0.1, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()
    p1 = flint.get_live_plot("default-curve")
    assert diode2.fullname in flint.test_displayed_channel_names(p1.plot_id)


def test_update_user_data(test_session_with_flint):
    session = test_session_with_flint
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
    flint = plot.get_flint()

    logger = logging.getLogger("flint.output")
    logger.disabled = False
    logger.setLevel(logging.INFO)

    ascan(roby, 0, 5, 2, 0.001, diode, diode2)

    # synchronize redis events with flint
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot("default-curve")

    data = numpy.arange(3)
    # Create on selected item
    p1.update_user_data("foo", diode.fullname, data)
    # Create on non-selected item
    p1.update_user_data("foo", diode2.fullname, data)
    # Remove
    p1.update_user_data("foo", diode.fullname, None)
    # Remove a non-existing item
    p1.update_user_data("foo2", diode.fullname, None)

    gevent.sleep(1)
    assert flint.test_count_displayed_items(p1.plot_id) == 2


def test_sequence(test_session_with_flint, lima_simulator):
    session = test_session_with_flint
    lima = session.config.get("lima_simulator")
    ascan = session.env_dict["ascan"]
    roby = session.config.get("roby")
    diode = session.config.get("diode")

    flint = plot.get_flint()

    scan_info = ScanInfo()
    scan_info.add_scatter_plot(x="x", y="y", value="diode")

    seq = Sequence(scan_info=scan_info)
    with seq.sequence_context() as scan_seq:
        s = ascan(roby, 0, 5, 5, 0.001, diode, lima, run=False)
        scan_seq.add(s)
        s.run()

    flint.wait_end_of_scans()

    p1_data = flint.get_live_scan_data("axis:roby")
    p2_data = flint.get_live_scan_data(diode.fullname)
    p3_data = flint.get_live_scan_data(lima.image.fullname)

    assert len(p1_data) == 6  # 5 intervals
    assert len(p2_data) == 6  # 5 intervals
    assert numpy.allclose(p1_data, numpy.arange(6))
    assert len(p3_data.shape) == 2


def create_1d_controller(device_name, fixed_xarray=False, fixed_xchannel=False):
    class OneDimAcquisitionSlave(SamplingCounterAcquisitionSlave):
        def fill_meta_at_scan_start(self, scan_meta):
            def get_channel_by_counter_name(name):
                for counter, channels in self._counters.items():
                    if counter.name == name:
                        return channels[0]
                return None

            if fixed_xarray:
                meta = {"xaxis_array": numpy.arange(32) * 10}
            elif fixed_xchannel:
                xaxis_channel = get_channel_by_counter_name("d2")
                meta = {"xaxis_channel": xaxis_channel.fullname}
            else:
                meta = None
            return meta

    class OneDimController(simulation_counter.OneDimSimulationController):
        def __init__(self):
            simulation_counter.OneDimSimulationController.__init__(
                self, name=device_name
            )
            simulation_counter.OneDimSimulationCounter(
                name="d1", controller=self, signal="gaussian", coef=100, poissonian=True
            )
            simulation_counter.OneDimSimulationCounter(
                name="d2", controller=self, signal="linear_up", coef=100
            )

        def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
            return OneDimAcquisitionSlave(self, ctrl_params=ctrl_params, **acq_params)

    return OneDimController()


def test_onedim_controller(test_session_with_flint):
    session = test_session_with_flint
    ct = session.env_dict["ct"]
    controller = create_1d_controller("det")

    flint = plot.get_flint()

    # p2_data = flint.get_live_scan_data(diode.fullname)
    # p3_data = flint.get_live_scan_data(lima.image.fullname)

    ct(0.1, controller)
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot(onedim_detector="det")
    assert p1 is not None
    p1_data = flint.get_live_scan_data("det:d1")
    p2_data = flint.get_live_scan_data("det:d2")
    assert len(p1_data) == 32
    assert len(p2_data) == 32


def test_onedim_controller__fixed_xarray(test_session_with_flint):
    session = test_session_with_flint
    ct = session.env_dict["ct"]
    controller = create_1d_controller("det", fixed_xarray=True)

    flint = plot.get_flint()

    # p2_data = flint.get_live_scan_data(diode.fullname)
    # p3_data = flint.get_live_scan_data(lima.image.fullname)

    ct(0.1, controller)
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot(onedim_detector="det")
    assert p1 is not None
    p1_data = flint.get_live_scan_data("det:d1")
    p2_data = flint.get_live_scan_data("det:d2")
    assert len(p1_data) == 32
    assert len(p2_data) == 32


def test_onedim_controller__fixed_xchannel(test_session_with_flint):
    session = test_session_with_flint
    ct = session.env_dict["ct"]
    controller = create_1d_controller("det", fixed_xchannel=True)

    flint = plot.get_flint()

    # p2_data = flint.get_live_scan_data(diode.fullname)
    # p3_data = flint.get_live_scan_data(lima.image.fullname)

    ct(0.1, controller)
    flint.wait_end_of_scans()

    p1 = flint.get_live_plot(onedim_detector="det")
    assert p1 is not None
    p1_data = flint.get_live_scan_data("det:d1")
    p2_data = flint.get_live_scan_data("det:d2")
    assert len(p1_data) == 32
    assert len(p2_data) == 32
