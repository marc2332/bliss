# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
import time
import numpy
from bliss.common import scans
from bliss.scanning import scan, chain
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.acquisition import timer, calc, motor, counter
from bliss.common import event, scans
from bliss.controllers.counter import CalcCounterController


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
    simul_counter = session.env_dict["sim_ct_gauss"]
    points = [0.0, 0.1, 0.3, 0.7]
    s = scans.pointscan(robz2, points, 0, simul_counter, return_scan=True, save=False)
    assert robz2.position == 0.7
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["robz2"], points)
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_lookupscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    diode = session.env_dict["diode"]
    s = scans.lookupscan(0.1, roby, (0, 0.1), robz, (0.1, 0.2), diode, save=False)
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["roby"], (0, 0.1))
    assert numpy.array_equal(scan_data["robz"], (0.1, 0.2))


def test_anscan(session):
    roby = session.env_dict["roby"]
    robz = session.env_dict["robz"]
    diode = session.env_dict["diode"]
    s = scans.anscan(0.1, 1, roby, 0, 0.1, robz, 0.1, 0.2, diode, save=False)
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

    scans.ascan(roby, 0, 9, 9, 0.01, diode)
    captured = capsys.readouterr()

    assert captured.out == "scan_new\n" + "scan_data\n" * 10 + "scan_end\n"


def test_scan_watch_data_no_print_on_saferef(session, capsys):
    """
    In the previous function
    'test_scan_watch_data_set_callback_to_test_saferef', we set a
    callback on scan_new event that produces a print.
    Thanks to the underlying usage of a weakref, the print should not
    append once we get out of the context of the previous function.
    """
    roby = session.config.get("roby")
    diode = session.config.get("diode")
    scans.ascan(roby, 0, 10, 10, 0.01, diode)
    captured = capsys.readouterr()

    assert captured.out == ""


def test_calc_counters(session):
    robz2 = session.env_dict["robz2"]
    c = chain.AcquisitionChain()
    cnt = session.env_dict["sim_ct_gauss"]

    # To force (lazy) initialization of sim_ct_1 ...
    s = scans.ascan(robz2, 0, 0.1, 2, 0, cnt, return_scan=True, save=False)

    t = timer.SoftwareTimerMaster(0, npoints=2)

    # get the acq device of simulatiion counter and add it to the chain
    cnt_acq_device = cnt.get_acquisition_device()
    c.add(t, cnt_acq_device)

    # Creates a calc counter which returns the square of the original counter
    calc_cnt = calc.CalcAcquisitionSlave(
        "bla",
        (cnt_acq_device,),
        lambda y, x: {"pow": x["sim_ct_gauss"] ** 2},
        (AcquisitionChannel("pow", numpy.float, ()),),
    )
    c.add(t, calc_cnt)
    top_master = motor.LinearStepTriggerMaster(2, robz2, 0, 1)
    c.add(top_master, t)

    s = scan.Scan(c, name="calc_scan", save=False)
    s.run()
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["sim_ct_gauss"] ** 2, scan_data["pow"])


def test_calc_counter_callback(session):
    m1 = session.env_dict["m1"]
    c = chain.AcquisitionChain()
    cnt = session.env_dict["sim_ct_gauss"]

    # To force (lazy) initialization of sim_ct_1 ...
    s = scans.ascan(m1, 0, 0.1, 10, 0, cnt, return_scan=True, save=False)

    t = timer.SoftwareTimerMaster(0, npoints=10)
    cnt_acq_device = cnt.get_acquisition_device()
    c.add(t, cnt_acq_device)

    class CBK(calc.CalcHook):
        def __init__(self):
            self.prepare_called = 0
            self.start_called = 0
            self.stop_called = 0

        def compute(self, sender, data_dict):
            return {"pow": data_dict["sim_ct_gauss"] ** 2}

        def prepare(self):
            self.prepare_called += 1

        def start(self):
            self.start_called += 1

        def stop(self):
            self.stop_called += 1

    cbk = CBK()
    calc_cnt = calc.CalcAcquisitionSlave(
        "bla", (cnt_acq_device,), cbk, (AcquisitionChannel("pow", numpy.float, ()),)
    )
    c.add(t, calc_cnt)
    top_master = motor.LinearStepTriggerMaster(10, m1, 0, 1)
    c.add(top_master, t)

    s = scan.Scan(c, name="calc_scan", save=False)
    s.run()
    assert cbk.prepare_called == 10
    assert cbk.start_called == 10
    assert cbk.stop_called == 1


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
    assert "simulation_diode_controller" in timer_channels
    assert (
        "diode"
        in list(timer_channels["simulation_diode_controller"].children())[0].name
    )


def test_calc_counters_std_scan(session):
    robz2 = session.env_dict["robz2"]
    cnt = session.env_dict["sim_ct_gauss"]
    calc_name = f"pow2_{cnt.name}"
    variables = {"nb_points": 0}

    def pow2(sender, data_dict):
        variables["nb_points"] += 1
        return {calc_name: data_dict["sim_ct_gauss"] ** 2}

    calc_counter_controller = CalcCounterController(calc_name, pow2, cnt)
    s = scans.ascan(robz2, 0, .1, 9, 0, calc_counter_controller, save=False)
    assert variables["nb_points"] == 10
    data = s.get_data()
    src_data = {"sim_ct_gauss": data["sim_ct_gauss"]}
    # use of the magic '==' operator of numpy arrays, make a one-by-one
    # comparison and returns the result in a list
    assert all(data[calc_name] == pow2(None, src_data)[calc_name])


def test_calc_counters_with_two(session):
    calc_name = "mean"

    class Mean(calc.CalcHook):
        def prepare(self):
            self.data = {}

        def compute(self, sender, data_dict):
            nb_point_to_emit = numpy.inf
            for cnt_name in ("diode", "diode2"):
                cnt_data = data_dict.get(cnt_name, [])
                data = self.data.get(cnt_name, [])
                if len(cnt_data):
                    data = numpy.append(data, cnt_data)
                    self.data[cnt_name] = data
                nb_point_to_emit = min(nb_point_to_emit, len(data))
            if not nb_point_to_emit:
                return
            mean_data = (
                self.data["diode"][:nb_point_to_emit]
                + self.data["diode2"][:nb_point_to_emit]
            ) / 2.
            self.data = {
                key: data[nb_point_to_emit:] for key, data in self.data.items()
            }
            return {calc_name: mean_data}

    robz2 = session.env_dict["robz2"]
    diode = session.env_dict["diode"]
    diode2 = session.env_dict["diode2"]
    mean_func = Mean()
    mean_counter_controller = CalcCounterController(calc_name, mean_func, diode, diode2)
    s = scans.ascan(robz2, 0, .1, 10, 0, mean_counter_controller, save=False)
    data = s.get_data()
    assert all(data[calc_name] == (data["diode"] + data["diode2"]) / 2.)
