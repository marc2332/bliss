# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import mock
import pytest
import time
import numpy
import gevent
from bliss.common import scans, event
from bliss.scanning import scan
from bliss.controllers.counter import CalcCounterController
from bliss.scanning.acquisition.calc import CalcCounterAcquisitionSlave


def test_ascan(session):
    robz2 = session.env_dict["robz2"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.ascan(
        robz2, 0, 0.1234567, 2, 0, simul_counter, return_scan=True, save=False
    )
    assert pytest.approx(robz2.position, abs=0.0001) == 0.1234567
    # test for issue #1079
    # use tolerance to get axis precision
    assert pytest.approx(robz2.tolerance) == 1e-4
    assert s.scan_info["title"].startswith("ascan robz2 0 0.1235 ")
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)

    # A default plot is expected, displaying the motor as x-axis
    plot = s.scan_info["plots"][0]
    assert plot["items"][0]["x"] == "axis:robz2"


def test_loopscan_sleep_time(session):
    simul_counter = session.env_dict["sim_ct_gauss"]

    s = scans.loopscan(2, 0.2, simul_counter, sleep_time=1, save=False, run=False)

    timer = s.acq_chain.top_masters[0]
    assert timer.sleep_time == 1

    with mock.patch.object(timer, "_sleep", wraps=timer._sleep) as timer_sleep:
        s.run()
        assert timer_sleep.call_count == 1

    # A default plot is expected, displaying the time as x-axis
    plot = s.scan_info["plots"][0]
    assert plot["items"][0]["x"] == "timer:elapsed_time"


def test_ascan_gauss2(session):
    robz2 = session.env_dict["robz2"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.ascan(robz2, 0, 0.1, 2, 0, simul_counter, return_scan=True, save=False)
    assert robz2.position == 0.1
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_ascan_encoder_in_counters(session):
    # issue #1990
    m1 = session.env_dict["m1"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.ascan(m1, 0, 0.1, 2, 0, simul_counter, return_scan=True, save=False)
    scan_data = s.get_data()
    assert "encoder:m1enc" in scan_data


def test_dscan(session):
    simul_counter = session.env_dict["sim_ct_gauss"]
    robz2 = session.env_dict["robz2"]
    robz2.position = 0.1265879
    # contrary to ascan, dscan returns to start pos
    start_pos = robz2.position
    s = scans.dscan(robz2, -0.2, 0.2, 1, 0, simul_counter, return_scan=True, save=False)
    # test for issues #1080
    # use tolerance to get axis precision
    assert pytest.approx(robz2.tolerance) == 1e-4
    assert s.scan_info["title"].startswith(
        f"ascan robz2 {start_pos - 0.2:.4f} {start_pos + 0.2:.4f}"
    )
    #
    assert robz2.position == start_pos
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["robz2"],
        numpy.linspace(start_pos - 0.2, start_pos + 0.2, 2),
        atol=5e-4,
    )
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_d2scan(session):
    simul_counter = session.env_dict["sim_ct_gauss"]
    robz = session.env_dict["robz"]
    robz.position = 1
    robz2 = session.env_dict["robz2"]
    robz2.position = -1
    # contrary to ascan, dscan returns to start pos
    start_pos = robz2.position
    s = scans.d2scan(
        robz2,
        -0.2,
        0.2,
        robz,
        -0.1,
        0.1,
        1,
        0,
        simul_counter,
        return_scan=True,
        save=False,
    )
    # test for issues #1080
    # use tolerance to get axis precision
    assert pytest.approx(robz2.tolerance) == 1e-4
    assert s.scan_info["title"].startswith("a2scan robz2 -1.2 -0.8")
    #
    assert robz2.position == start_pos
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["robz2"],
        numpy.linspace(start_pos - 0.2, start_pos + 0.2, 2),
        atol=5e-4,
    )
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)

    channels = s.scan_info["channels"]
    assert channels["axis:robz2"]["start"] == pytest.approx(-1.2)
    assert channels["axis:robz2"]["stop"] == pytest.approx(-0.8)
    assert channels["axis:robz"]["start"] == pytest.approx(0.9)
    assert channels["axis:robz"]["stop"] == pytest.approx(1.1)


def test_lineup(session):
    simul_counter = session.env_dict["sim_ct_gauss"]
    robz2 = session.env_dict["robz2"]
    start_pos = robz2.position
    s = scans.lineup(
        robz2, -0.2, 0.2, 2, 0, simul_counter, return_scan=True, save=False
    )
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["robz2"],
        numpy.linspace(start_pos - 0.2, start_pos + 0.2, 3),
        atol=5e-4,
    )
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)
    # after lineup motor goes to where the counter has its max value
    assert robz2.position == 0


def test_dscan_move_done(session):
    simul_counter = session.env_dict["sim_ct_gauss"]
    robz2 = session.env_dict["robz2"]

    # Callback
    positions = []

    def target(done):
        if done:
            positions.append(robz2.dial)

    event.connect(robz2, "move_done", target)

    # contrary to ascan, dscan returns to start pos
    start_pos = robz2.position
    s = scans.dscan(robz2, -0.2, 0.2, 1, 0, simul_counter, return_scan=True, save=False)
    assert robz2.position == start_pos
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["robz2"],
        numpy.linspace(start_pos - 0.2, start_pos + 0.2, 2),
        atol=5e-4,
    )
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)
    assert positions[0] == -0.2
    assert positions[-2] == 0.2
    assert positions[-1] == 0

    event.disconnect(robz2, "move_done", target)


def test_pointscan(session):
    robz2 = session.env_dict["robz2"]
    diode = session.env_dict["diode"]
    points = [0.0, 0.1, 0.3, 0.7]
    s = scans.pointscan(robz2, points, 0, diode, save=False, run=False)
    assert s.state == scan.ScanState.IDLE
    s.run()
    assert robz2.position == 0.7
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["robz2"], points)
    assert diode.fullname in scan_data


def test_lookupscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    diode = session.env_dict["diode"]
    s = scans.lookupscan([(roby, (0, 0.1)), (robz, (0.1, 0.2))], 0.1, diode, save=False)
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["roby"], (0, 0.1))
    assert numpy.array_equal(scan_data["robz"], (0.1, 0.2))

    # A default plot is expected, displaying the time as x-axis
    plot = s.scan_info["plots"][0]
    assert plot["items"][0]["x"] == "timer:elapsed_time"


def test_anscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    diode = session.env_dict["diode"]
    s = scans.anscan([(roby, 0, 0.1), (robz, 0.1, 0.2)], 1, 0.1, diode, save=False)
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["roby"], (0, 0.1))
    assert numpy.array_equal(scan_data["robz"], (0.1, 0.2))


def test_all_anscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    robz2 = session.env_dict["robz2"]
    m0 = session.env_dict["m0"]
    m1 = session.env_dict["m1"]
    diode = session.env_dict["diode"]
    # just call them to check syntax
    # real test is done else where
    scans.a5scan(
        roby,
        0,
        0.1,
        robz,
        0,
        0.1,
        robz2,
        0,
        0.1,
        m0,
        0,
        0.1,
        m1,
        0,
        0.1,
        2,
        0.1,
        diode,
        save=False,
        run=False,
    )
    scans.a4scan(
        roby,
        0,
        0.1,
        robz,
        0,
        0.1,
        robz2,
        0,
        0.1,
        m0,
        0,
        0.1,
        2,
        0.1,
        diode,
        save=False,
        run=False,
    )
    scans.a3scan(
        roby, 0, 0.1, robz, 0, 0.1, robz2, 0, 0.1, 2, 0.1, diode, save=False, run=False
    )


def test_all_dnscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    robz2 = session.env_dict["robz2"]
    m0 = session.env_dict["m0"]
    m1 = session.env_dict["m1"]
    diode = session.env_dict["diode"]
    # just call them to check syntax
    # real test is done else where
    scans.d5scan(
        roby,
        0,
        0.1,
        robz,
        0,
        0.1,
        robz2,
        0,
        0.1,
        m0,
        0,
        0.1,
        m1,
        0,
        0.1,
        2,
        0.1,
        diode,
        save=False,
        run=False,
    )
    scans.d4scan(
        roby,
        0,
        0.1,
        robz,
        0,
        0.1,
        robz2,
        0,
        0.1,
        m0,
        0,
        0.1,
        2,
        0.1,
        diode,
        save=False,
        run=False,
    )
    scans.d3scan(
        roby, 0, 0.1, robz, 0, 0.1, robz2, 0, 0.1, 2, 0.1, diode, save=False, run=False
    )


def test_scan_watch_data_no_print(session, capsys):
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    scans.ascan(roby, 0, 10, 10, 0.01, diode, save=False)
    captured = capsys.readouterr()

    assert captured.out == ""


def test_scan_watch_data_callback_not_a_callable():
    a = 5
    with pytest.raises(TypeError):
        scan.set_scan_watch_callbacks(scan_new=a, scan_data=None, scan_end=None)
    with pytest.raises(TypeError):
        scan.set_scan_watch_callbacks(scan_new=None, scan_data=a, scan_end=None)
    with pytest.raises(TypeError):
        scan.set_scan_watch_callbacks(scan_new=None, scan_data=None, scan_end=a)


def test_scan_callbacks(session):

    res = {"new": False, "end": False, "values1": [], "values2": [], "values3": []}

    def on_scan_new(scan, scan_info):
        res["new"] = True

    def on_scan_data(scan_info, values):
        # values is indexed by *channel* full name
        res["values1"].append(values[simul_counter1.fullname])
        res["values2"].append(values[simul_counter2.fullname])
        res["values3"].append(values[simul_counter3.fullname])

    def on_scan_end(scan_info):
        res["end"] = True

    scan.set_scan_watch_callbacks(on_scan_new, on_scan_data, on_scan_end)

    simul_counter1 = session.env_dict["sim_ct_gauss"]
    simul_counter2 = session.env_dict["sim_ct_gauss_noise"]
    simul_counter3 = session.env_dict["sim_ct_rand_12"]

    scans.timescan(
        0.1,
        simul_counter1,
        simul_counter2,
        simul_counter3,
        npoints=17,
        return_scan=True,
        save=False,
    )
    assert res["new"]
    assert res["end"]
    assert numpy.array_equal(numpy.array(res["values1"]), simul_counter1.data)
    assert numpy.array_equal(numpy.array(res["values2"]), simul_counter2.data)
    assert numpy.array_equal(numpy.array(res["values3"]), simul_counter3.data)


def test_timescan_with_lima(default_session, lima_simulator):
    ls = default_session.config.get("lima_simulator")
    s = scans.timescan(0.01, ls, save=False, run=False)
    try:
        g = gevent.spawn(s.run)

        s.wait_state(scan.ScanState.STARTING)

        gevent.sleep(0.3)  # let time to take some images...
    finally:
        g.kill()

    assert len(s.get_data()[ls.image]) > 1


def test_scan_watch_data_set_callback_to_test_saferef(session, capsys):
    roby = session.config.get("roby")
    diode = session.config.get("diode")

    def on_scan_new(*args):
        print("scan_new")

    def on_scan_data(*args):
        print("scan_data")

    def on_scan_end(*args):
        print("scan_end")

    scan.set_scan_watch_callbacks(on_scan_new, on_scan_data, on_scan_end)

    scans.ascan(roby, 0, 1, 13, 0.01, diode, save=False)

    captured = capsys.readouterr()
    assert captured.out == "scan_new\n" + "scan_data\n" * 14 + "scan_end\n"

    del on_scan_new
    del on_scan_data
    del on_scan_end

    scans.ascan(roby, 0, 1, 5, 0.01, diode, save=False)

    captured = capsys.readouterr()
    assert captured.out == ""


def test_calc_counters(session):
    robz2 = session.env_dict["robz2"]
    cnt = session.env_dict["sim_ct_gauss"]

    class MyCCC(CalcCounterController):
        def calc_function(self, input_dict):
            return {"pow": input_dict["sim_ct_gauss"] ** 2}

    config = {
        "inputs": [{"counter": cnt, "tags": "sim_ct_gauss"}],
        "outputs": [{"name": "pow"}],
    }

    ccc = MyCCC("pow2", config)

    s = scans.ascan(robz2, 0, 1, 2, 0.1, ccc, return_scan=True, save=False)
    scan_data = s.get_data()

    assert numpy.array_equal(scan_data["sim_ct_gauss"] ** 2, scan_data["pow"])


def test_calc_counter_callback(session):
    m1 = session.env_dict["m1"]
    cnt = session.env_dict["sim_ct_gauss"]

    class CCAS(CalcCounterAcquisitionSlave):
        def prepare(self):
            super().prepare()
            self.device.prepare_called += 1

        def start(self):
            super().start()
            self.device.start_called += 1

        def stop(self):
            self.device.stop_called += 1
            super().stop()

    class MyCCC(CalcCounterController):
        def __init__(self, name, config):
            super().__init__(name, config)
            self.prepare_called = 0
            self.start_called = 0
            self.stop_called = 0

        def calc_function(self, input_dict):
            return {"pow": input_dict["sim_ct_gauss"] ** 2}

        def get_acquisition_object(
            self, acq_params, ctrl_params, parent_acq_params, acq_devices
        ):
            return CCAS(self, acq_devices, acq_params, ctrl_params=ctrl_params)

    config = {
        "inputs": [{"counter": cnt, "tags": "sim_ct_gauss"}],
        "outputs": [{"name": "pow"}],
    }

    ccc = MyCCC("pow2", config)

    scans.ascan(m1, 0, 1, 9, 0.1, ccc, save=False)

    assert ccc.prepare_called == 10
    assert ccc.start_called == 10
    assert ccc.stop_called == 1


def test_save_images(session, beacon, lima_simulator):
    lima_sim = beacon.get("lima_simulator")
    robz2 = session.env_dict["robz2"]
    scan_saving = session.scan_saving
    scan_saving.images_path_template = ""

    s = scans.ascan(robz2, 0, 1, 2, 0.001, lima_sim, run=False)
    scan_path = s.writer.filename
    images_path = os.path.dirname(scan_path)
    image_filename = "lima_simulator_000%d.edf"

    s.run()

    assert os.path.isfile(scan_path)
    for i in range(2):
        assert os.path.isfile(os.path.join(images_path, image_filename % i))

    os.unlink(scan_path)
    os.unlink(os.path.join(images_path, image_filename % 0))

    s = scans.ascan(robz2, 1, 0, 2, 0.001, lima_sim, save_images=False, run=False)

    s.run()

    scan_path = s.writer.filename
    assert os.path.isfile(scan_path)
    assert not os.path.isfile(os.path.join(scan_saving.base_path, image_filename % 0))

    os.unlink(scan_path)

    s = scans.ascan(
        robz2, 0, 1, 2, 0.001, lima_sim, save=False, save_images=True, run=False
    )

    s.run()

    scan_path = s.writer.filename
    assert not os.path.isfile(scan_path)
    assert not os.path.isfile(os.path.join(images_path, image_filename % 0))


def test_motor_group(session):
    diode = session.config.get("diode")
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    scan = scans.a2scan(roby, 0, 1, robz, 0, 1, 5, 0.1, diode, save=False)

    children = list(scan.node.children())
    axis_master = children[0]
    assert axis_master.name == "axis"
    items = dict((child.name, child) for child in axis_master.children())

    assert items["axis:roby"].parent.db_name == scan.node.db_name + ":axis"
    assert items["axis:robz"].parent.db_name == scan.node.db_name + ":axis"
    assert items["timer"].parent.db_name == scan.node.db_name + ":axis"
    timer_channels = dict((chan.name, chan) for chan in items["timer"].children())
    assert "timer:elapsed_time" in timer_channels
    assert "simulation_diode_sampling_controller" in timer_channels
    assert (
        "diode"
        in list(timer_channels["simulation_diode_sampling_controller"].children())[
            0
        ].name
    )


def test_calc_counters_std_scan(session):
    robz2 = session.env_dict["robz2"]
    cnt = session.env_dict["sim_ct_gauss"]
    variables = {"nb_points": 0}

    class MyCCC(CalcCounterController):
        def calc_function(self, input_dict):
            variables["nb_points"] += 1
            return {"out": input_dict["sim_ct_gauss"] ** 2}

    config = {
        "inputs": [{"counter": cnt, "tags": "sim_ct_gauss"}],
        "outputs": [{"name": "out"}],
    }

    calc_counter_controller = MyCCC("pow2", config)

    s = scans.ascan(robz2, 0, .1, 9, 0, calc_counter_controller, save=False)
    assert variables["nb_points"] == 10
    data = s.get_data()
    # use of the magic '==' operator of numpy arrays, make a one-by-one
    # comparison and returns the result in a list
    assert all(data["out"] == data["sim_ct_gauss"] ** 2)


def test_calc_counters_with_two(session):
    robz2 = session.env_dict["robz2"]
    diode = session.env_dict["diode"]
    diode2 = session.env_dict["diode2"]

    class MyCCC(CalcCounterController):
        def calc_function(self, input_dict):
            data_out = (input_dict["data1"] + input_dict["data2"]) / 2.
            return {"out": data_out}

    config = {
        "inputs": [
            {"counter": diode, "tags": "data1"},
            {"counter": diode2, "tags": "data2"},
        ],
        "outputs": [{"name": "out"}],
    }

    mean_counter_controller = MyCCC("mean", config)

    s = scans.ascan(robz2, 0, .1, 10, 0, mean_counter_controller, save=False)
    data = s.get_data()
    assert all(data["out"] == (data["diode"] + data["diode2"]) / 2.)


def check_typeguard(valid, motor, *counters, myint=3, myfloat=.1):
    if valid:
        s = scans.dscan(motor, -.1, .1, myint, myfloat, *counters, run=False)
    else:
        with pytest.raises(RuntimeError):
            s = scans.dscan(motor, -.1, .1, myint, myfloat, *counters, run=False)


def test_typeguard_scanable(default_session):
    diode = default_session.config.get("diode")
    m0 = default_session.config.get("m0")
    check_typeguard(True, m0, diode)
    check_typeguard(False, diode, diode)
    check_typeguard(False, m0, m0)
    check_typeguard(True, m0, diode, myint=int(3), myfloat=float(.1))
    check_typeguard(True, m0, diode, myint=numpy.uint8(3), myfloat=numpy.float64(.1))
    check_typeguard(True, m0, diode, myint=numpy.uint8(3), myfloat=1)
    check_typeguard(True, m0, diode, myint=numpy.uint8(3), myfloat=numpy.uint8(1))


def test_typeguardTypeError_to_hint():
    with pytest.raises(RuntimeError) as e:
        scans.ascan(1, 2, 3, 4, 5)
    assert (
        str(e.value)
        == 'Intended Usage: ascan(motor, start, stop, intervals, count_time, counter_args)  Hint: type of argument "motor" must be bliss.common.protocols.Scannable; got int instead'
    )

    import typeguard
    from bliss.common.utils import typeguardTypeError_to_hint

    @typeguardTypeError_to_hint
    @typeguard.typechecked
    def func(a: int):
        raise TypeError("blablabla")
        return True

    with pytest.raises(RuntimeError):
        func(1.5)

    with pytest.raises(TypeError):
        func(1)


def test_update_ctrl_params(default_session, beacon, lima_simulator):
    lima_sim = beacon.get("lima_simulator")

    s = scans.loopscan(1, .1, lima_sim, run=False)
    with pytest.raises(RuntimeError):
        s.update_ctrl_params(lima_sim, {"unkown_key": "bla"})

    s.update_ctrl_params(lima_sim, {"saving_format": "EDFGZ"})
    s.run()

    lima_data_view = s.get_data()["lima_simulator:image"]
    assert lima_data_view.image_reference(0)[0][-7:] == ".edf.gz"


def test_dscan_return_to_target_pos(default_session, beacon):
    m0 = beacon.get("m0")
    diode = beacon.get("diode")
    m0.move(1.5)
    s = scans.dscan(m0, -1.1, 1.1, 2, 0, diode, save=False)
    assert pytest.approx(m0._set_position) == 1.5
    d = s.get_data()
    assert min(d[m0]) == pytest.approx(0.0)
    assert max(d[m0]) == pytest.approx(3.0)


def test_ct_sct(session, beacon):
    diode = beacon.get("diode")
    ct = scans.ct(.1, diode)
    sct = scans.sct(.1, diode)
    assert ct.scan_info["save"] == False
    assert ct.node.info["save"] == False

    assert sct.scan_info["save"] == True
    assert sct.node.info["save"] == True

    assert "positioners" in sct.scan_info
    assert "positioners" not in ct.scan_info

    assert len(session.scans) == 1  # only sct in scans


@pytest.mark.parametrize("scan_type", ["anscan", "lookupscan", "anmesh"])
def test_duplicated_motor_in_multiple_motor_scan(session, beacon, scan_type):
    # fix for issue 1564
    diode = beacon.get("diode")
    roby = beacon.get("roby")
    robz = beacon.get("robz")
    scan_func = getattr(scans, scan_type)
    # the ranges, diode and count time won't be used, normally - should be stopped before
    if scan_type == "anscan":
        args = (((roby, 0, 1), (robz, 0, 1), (roby, 0, 1)), 10, 0.1, diode)
    elif scan_type == "lookupscan":
        args = (((roby, (0, 1)), (robz, (0, 1)), (roby, (0, 1))), 0.1, diode)
    elif scan_type == "anmesh":
        args = (((roby, 0, 1, 10), (robz, 0, 1, 10), (roby, 0, 1, 10)), 0.1, diode)
    with pytest.raises(ValueError) as excinfo:
        scan_func(*args, run=False)
    assert "Duplicated axis" in str(excinfo)
