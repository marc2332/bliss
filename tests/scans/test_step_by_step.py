# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
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
    assert pytest.approx(robz2.position, 0.1234567)
    # test for issue #1079
    # use tolerance to get axis precision
    assert pytest.approx(robz2.tolerance, 1e-4)
    assert s.scan_info["title"].startswith("ascan robz2 0 0.1235 ")
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_ascan_gauss2(session):
    robz2 = session.env_dict["robz2"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.ascan(robz2, 0, 0.1, 2, 0, simul_counter, return_scan=True, save=False)
    assert robz2.position == 0.1
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_dscan(session):
    simul_counter = session.env_dict["sim_ct_gauss"]
    robz2 = session.env_dict["robz2"]
    robz2.position = 0.1265879
    # contrary to ascan, dscan returns to start pos
    start_pos = robz2.position
    s = scans.dscan(robz2, -0.2, 0.2, 1, 0, simul_counter, return_scan=True, save=False)
    # test for issues #1080
    # use tolerance to get axis precision
    assert pytest.approx(robz2.tolerance, 1e-4)
    assert s.scan_info["title"].startswith("dscan robz2 -0.2 0.2")
    #
    assert robz2.position == start_pos
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["robz2"],
        numpy.linspace(start_pos - 0.2, start_pos + 0.2, 2),
        atol=5e-4,
    )
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


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


def test_anscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    diode = session.env_dict["diode"]
    s = scans.anscan([(roby, 0, 0.1), (robz, 0.1, 0.2)], 0.1, 1, diode, save=False)
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
    scans.ascan(roby, 0, 10, 10, 0.01, diode)
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

    res = {"new": False, "end": False, "values": []}

    def on_scan_new(scan, scan_info):
        res["new"] = True

    def on_scan_data(scan_info, values):
        # values is indexed by *channel* full name
        res["values"].append(values[simul_counter.fullname])

    def on_scan_end(scan_info):
        res["end"] = True

    scan.set_scan_watch_callbacks(on_scan_new, on_scan_data, on_scan_end)

    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.timescan(0.1, simul_counter, npoints=2, return_scan=True, save=False)
    assert res["new"]
    assert res["end"]
    assert numpy.array_equal(numpy.array(res["values"]), simul_counter.data)


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

    scans.ascan(roby, 0, 1, 3, 0.01, diode)

    captured = capsys.readouterr()
    assert captured.out == "scan_new\n" + "scan_data\n" * 4 + "scan_end\n"

    del on_scan_new
    del on_scan_data
    del on_scan_end

    scans.ascan(roby, 0, 1, 3, 0.01, diode)

    captured = capsys.readouterr()
    assert captured.out == ""


def test_scan_watch_callback_with_alias(alias_session):
    robyy = alias_session.env_dict["robyy"]
    diode = alias_session.config.get("diode")
    event_called = gevent.event.Event()

    def on_scan_new(*args):
        pass

    def on_scan_data(scan_info, values):
        motor_channel_name = f"axis:{robyy.name}"
        assert motor_channel_name in values
        event_called.set()

    def on_scan_end(*args):
        pass

    scan.set_scan_watch_callbacks(on_scan_new, on_scan_data, on_scan_end)

    scans.ascan(robyy, 0, 1, 2, 0.01, diode)

    with gevent.Timeout(1):
        event_called.wait()


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

        def get_acquisition_object(self, acq_params, ctrl_params, parent_acq_params):
            return CCAS(self, acq_params, ctrl_params=ctrl_params)

    config = {
        "inputs": [{"counter": cnt, "tags": "sim_ct_gauss"}],
        "outputs": [{"name": "pow"}],
    }

    ccc = MyCCC("pow2", config)

    scans.ascan(m1, 0, 1, 9, 0.1, ccc, save=False)

    assert ccc.prepare_called == 10
    assert ccc.start_called == 10
    assert ccc.stop_called == 1


def test_amesh(session):
    robz2 = session.env_dict["robz2"]
    robz = session.env_dict["robz"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.amesh(
        robz2,
        0,
        10,
        4,
        robz,
        0,
        5,
        2,
        0.01,
        simul_counter,
        return_scan=True,
        save=False,
    )
    assert robz2.position == 10
    assert robz.position == 5
    scan_data = s.get_data()
    assert len(scan_data["robz2"]) == 15
    assert len(scan_data["robz"]) == 15
    assert scan_data["robz2"][0] == 0
    assert scan_data["robz2"][4] == 10
    assert scan_data["robz2"][-1] == 10
    assert scan_data["robz"][0] == 0
    assert scan_data["robz"][-1] == 5
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_dmesh(session):
    robz2 = session.env_dict["robz2"]
    robz = session.env_dict["robz"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    start_robz2 = robz2.position
    start_robz = robz.position
    s = scans.dmesh(
        robz2,
        -5,
        5,
        4,
        robz,
        -3,
        3,
        2,
        0.01,
        simul_counter,
        return_scan=True,
        save=False,
    )
    assert robz2.position == start_robz2
    assert robz.position == start_robz
    scan_data = s.get_data()
    assert len(scan_data["robz2"]) == 15
    assert len(scan_data["robz"]) == 15
    assert scan_data["robz2"][0] == start_robz2 - 5
    assert scan_data["robz2"][-1] == start_robz2 + 5
    assert scan_data["robz"][0] == start_robz - 3
    assert scan_data["robz"][-1] == start_robz + 3
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_save_images(session, beacon, lima_simulator, scan_tmpdir):

    lima_sim = beacon.get("lima_simulator")
    robz2 = session.env_dict["robz2"]
    scan_saving = session.scan_saving
    saved_base_path = scan_saving.base_path
    try:
        scan_saving.base_path = str(scan_tmpdir)
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
        assert not os.path.isfile(
            os.path.join(scan_saving.base_path, image_filename % 0)
        )

        os.unlink(scan_path)

        s = scans.ascan(
            robz2, 0, 1, 2, 0.001, lima_sim, save=False, save_images=True, run=False
        )

        s.run()

        scan_path = s.writer.filename
        assert not os.path.isfile(scan_path)
        assert not os.path.isfile(os.path.join(images_path, image_filename % 0))
    finally:
        scan_saving.base_path = saved_base_path


def test_motor_group(session):
    diode = session.config.get("diode")
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    scan = scans.a2scan(roby, 0, 1, robz, 0, 1, 5, 0.1, diode)

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


def check_typeguard(valid, motor, *counters):
    if valid:
        s = scans.dscan(motor, -.1, .1, 3, .1, *counters, run=False)
    else:
        with pytest.raises(TypeError):
            s = scans.dscan(motor, -.1, .1, 3, .1, *counters, run=False)


def test_typeguard_scanable(default_session):
    diode = default_session.config.get("diode")
    m0 = default_session.config.get("m0")
    check_typeguard(True, m0, diode)
    check_typeguard(False, diode, diode)
    check_typeguard(False, m0, m0)
