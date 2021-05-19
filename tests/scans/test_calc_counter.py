# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# ----------------------------- TEST -----------------------------------------------------------
import numpy
import pytest
from bliss.common.scans import ascan, loopscan, dscan
from bliss.controllers.simulation_calc_counter import MeanCalcCounterController
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.acquisition.calc import CalcChannelAcquisitionSlave, CalcHook
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.channel import AcquisitionChannel


def test_calc_counter_from_config(default_session):

    cc1 = default_session.config.get("simul_calc_controller")
    cc2 = default_session.config.get("simul_calc_controller2")

    roby = default_session.config.get("roby")

    sc = ascan(roby, 0, 10, 10, 0.1, cc1, cc2)

    assert numpy.array_equal(
        sc.get_data()["out1"], (sc.get_data()["diode"] + sc.get_data()["diode2"]) / 2.
    )

    assert numpy.array_equal(
        sc.get_data()["out2"],
        (sc.get_data()["deadtime_det0"] + sc.get_data()["deadtime_det1"]) / 2.,
    )


def test_calc_counter_on_the_fly(default_session):

    # --- make calc counters ------------------------
    diode1 = default_session.config.get("diode")
    diode2 = default_session.config.get("diode2")
    diode3 = default_session.config.get("diode3")
    diode4 = default_session.config.get("diode4")
    diode5 = default_session.config.get("diode5")
    diode6 = default_session.config.get("diode6")
    diode7 = default_session.config.get("diode7")

    cc6 = MeanCalcCounterController(
        "cc6",
        {
            "inputs": [{"counter": diode1}, {"counter": diode2}],
            "outputs": [{"name": "cc6"}],
        },
    )
    cc5 = MeanCalcCounterController(
        "cc5",
        {
            "inputs": [{"counter": diode4}, {"counter": diode5}],
            "outputs": [{"name": "cc5"}],
        },
    )
    cc4 = MeanCalcCounterController(
        "cc4",
        {
            "inputs": [{"counter": diode6}, {"counter": diode7}],
            "outputs": [{"name": "cc4"}],
        },
    )
    cc3 = MeanCalcCounterController(
        "cc3",
        {
            "inputs": [{"counter": cc6.counters[0]}, {"counter": diode3}],
            "outputs": [{"name": "cc3"}],
        },
    )
    cc2 = MeanCalcCounterController(
        "cc2",
        {
            "inputs": [{"counter": cc5.counters[0]}, {"counter": cc4.counters[0]}],
            "outputs": [{"name": "cc2"}],
        },
    )
    cc1 = MeanCalcCounterController(
        "cc1",
        {
            "inputs": [{"counter": cc3.counters[0]}, {"counter": cc2.counters[0]}],
            "outputs": [{"name": "cc1"}],
        },
    )

    roby = default_session.config.get("roby")

    sc = ascan(roby, 0, 10, 10, 0.1, cc1)

    assert numpy.array_equal(
        sc.get_data()["cc6"], (sc.get_data()["diode"] + sc.get_data()["diode2"]) / 2.
    )
    assert numpy.array_equal(
        sc.get_data()["cc5"], (sc.get_data()["diode4"] + sc.get_data()["diode5"]) / 2.
    )
    assert numpy.array_equal(
        sc.get_data()["cc4"], (sc.get_data()["diode6"] + sc.get_data()["diode7"]) / 2.
    )
    assert numpy.array_equal(
        sc.get_data()["cc3"], (sc.get_data()["cc6"] + sc.get_data()["diode3"]) / 2.
    )
    assert numpy.array_equal(
        sc.get_data()["cc2"], (sc.get_data()["cc5"] + sc.get_data()["cc4"]) / 2.
    )
    assert numpy.array_equal(
        sc.get_data()["cc1"], (sc.get_data()["cc3"] + sc.get_data()["cc2"]) / 2.
    )


def test_calc_channels_convert_func(default_session):

    npoints = 11
    start = 0
    stop = 10
    count_time = 0.1

    roby = default_session.config.get("roby")

    acq_master = LinearStepTriggerMaster(npoints, roby, start, stop)

    chain = AcquisitionChain()

    # ----- build the calculated channel ------------------------------------------------------------------
    def func(sender, data_dict):
        return {"position": data_dict["roby"] * 0.1}

    # calc_chan_out = AcquisitionChannel("position", float, ())
    calc_chan_acq = CalcChannelAcquisitionSlave(
        "calc_chan_acq", [acq_master], func, ["position"]
    )

    chain.add(acq_master, calc_chan_acq)
    # -----------------------------------------------------------------------------------------------------

    scan_info = {
        "npoints": npoints,
        "count_time": count_time,
        "start": start,
        "stop": stop,
    }

    sc = Scan(
        chain,
        name="my_scan",
        scan_info=scan_info,
        save=False,
        save_images=False,
        scan_saving=None,
    )

    sc.run()

    assert numpy.array_equal(sc.get_data()["roby"] * 0.1, sc.get_data()["position"])


def test_calc_channels_mean_position(default_session):

    npoints = 11
    start = 0
    stop = 10
    count_time = 0.1

    roby = default_session.config.get("roby")

    acq_master = LinearStepTriggerMaster(npoints, roby, start, stop)

    chain = AcquisitionChain()

    # ----- build the calculated channel ------------------------------------------------------------------
    class MyHook(CalcHook):
        def __init__(self):
            self.last_data = None

        def compute(self, sender, data_dict):
            """ design for the simple case where data is received as a single value (not per block) """

            data = data_dict["roby"]

            if self.last_data is None:
                self.last_data = data[0]
                return

            start = self.last_data
            stop = data[-1]
            mean = (stop - start) / 2.
            self.last_data = stop
            return {"mean_pos": numpy.array([mean])}

    calc_chan_out = AcquisitionChannel("mean_pos", float, ())
    calc_chan_acq = CalcChannelAcquisitionSlave(
        "calc_chan_acq", [acq_master], MyHook(), [calc_chan_out]
    )

    chain.add(acq_master, calc_chan_acq)
    # -----------------------------------------------------------------------------------------------------

    scan_info = {
        "npoints": npoints,
        "count_time": count_time,
        "start": start,
        "stop": stop,
    }

    sc = Scan(
        chain,
        name="my_scan",
        scan_info=scan_info,
        save=False,
        save_images=False,
        scan_saving=None,
    )

    sc.run()

    assert numpy.array_equal(sc.get_data()["mean_pos"], numpy.ones((10,)) / 2.)


def test_single_calc_counter(default_session):
    mg1 = default_session.config.get("MG1")
    calc_counter_ctrl = default_session.config.get("simul_calc_controller2")
    calc_counter = calc_counter_ctrl.outputs.out2

    mg1.add(calc_counter)

    s = loopscan(1, .1, calc_counter_ctrl)
    s.get_data()["deadtime_det0"]
    s.get_data()["deadtime_det1"]
    s.get_data()["out2"]

    s = loopscan(1, .1, calc_counter)
    s.get_data()["deadtime_det0"]
    s.get_data()["deadtime_det1"]
    s.get_data()["out2"]

    s = loopscan(1, .1, mg1)
    s.get_data()["deadtime_det0"]
    s.get_data()["deadtime_det1"]
    s.get_data()["out2"]

    s = loopscan(1, .1)
    s.get_data()["deadtime_det0"]
    s.get_data()["deadtime_det1"]
    s.get_data()["out2"]


def test_expr_calc_counter(default_session):
    simu_expr_calc_ctrl = default_session.config.get("simu_expr_calc_ctrl")
    s = loopscan(1, .1, simu_expr_calc_ctrl, save=False)
    assert (
        s.get_data()["simu1:deadtime_det0"] * 10
        == s.get_data()["simu_expr_calc_ctrl:out3"]
    )
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode2"] * 100
        == s.get_data()["simu_expr_calc_ctrl:out4"]
    )

    simu_expr_calc = default_session.config.get("simu_expr_calc")
    s = loopscan(1, .1, simu_expr_calc, save=False)
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode"] * 10
        + s.get_data()["simulation_diode_sampling_controller:diode2"]
        == s.get_data()["simu_expr_calc_ctrl:simu_expr_calc"]
    )

    simu_expr_calc_no_constant = default_session.config.get(
        "simu_expr_calc_no_constant"
    )
    s = loopscan(1, .1, simu_expr_calc_no_constant, save=False)
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode"]
        + s.get_data()["simulation_diode_sampling_controller:diode2"]
        == s.get_data()["simu_expr_calc_no_constant_ctrl:simu_expr_calc_no_constant"]
    )


def test_expr_calc_counter_beaconobject(default_session):
    simu_expr_calc_ctrl = default_session.config.get("simu_expr_calc_ctrl")
    s = loopscan(1, .1, simu_expr_calc_ctrl, save=False)

    simu_expr_calc_ctrl.constants.m = 20
    s = loopscan(1, .1, simu_expr_calc_ctrl, save=False)
    assert (
        s.get_data()["simu1:deadtime_det0"] * 20
        == s.get_data()["simu_expr_calc_ctrl:out3"]
    )
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode2"] * 100
        == s.get_data()["simu_expr_calc_ctrl:out4"]
    )

    simu_expr_calc = default_session.config.get("simu_expr_calc")
    s = loopscan(1, .1, simu_expr_calc, save=False)
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode"] * 10
        + s.get_data()["simulation_diode_sampling_controller:diode2"]
        == s.get_data()["simu_expr_calc_ctrl:simu_expr_calc"]
    )

    simu_expr_calc.constants.m = 20
    s = loopscan(1, .1, simu_expr_calc, save=False)
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode"] * 20
        + s.get_data()["simulation_diode_sampling_controller:diode2"]
        == s.get_data()["simu_expr_calc_ctrl:simu_expr_calc"]
    )


def test_expr_calc_counter_with_ref(default_session):
    roby = default_session.config.get("roby")
    diode = default_session.config.get("diode")
    simu_expr_calc_ref = default_session.config.get("simu_expr_calc_ref")

    d = simu_expr_calc_ref.constants.to_dict()
    assert d["b"] == roby.position
    roby.rmove(1)
    d = simu_expr_calc_ref.constants.to_dict()
    assert d["b"] == roby.position

    s = dscan(roby, -.1, .1, 5, 0.001, simu_expr_calc_ref, save=False)
    assert numpy.array_equal(
        s.get_data()["simulation_diode_sampling_controller:diode"]
        + s.get_data()["axis:roby"],
        s.get_data()["simu_expr_calc_ref_ctrl:simu_expr_calc_ref"],
    )


def test_expr_calc_counter_with_alias(default_session):
    simu_expr_calc_ctrl = default_session.config.get("simu_expr_calc_ctrl")
    alias_out = default_session.env_dict["ALIASES"].add(
        "alias_out", simu_expr_calc_ctrl.counters.out3
    )
    s = loopscan(1, .1, alias_out, save=False)
    assert (
        s.get_data()["simu1:deadtime_det0"] * 10
        == s.get_data()["simu_expr_calc_ctrl:alias_out"]
    )
    simu_expr_calc = default_session.config.get("simu_expr_calc")
    alias_expr_calc = default_session.env_dict["ALIASES"].add(
        "alias_expr_calc", simu_expr_calc
    )
    s = loopscan(1, .1, alias_expr_calc, save=False)
    assert (
        s.get_data()["simulation_diode_sampling_controller:diode"] * 10
        + s.get_data()["simulation_diode_sampling_controller:diode2"]
        == s.get_data()["simu_expr_calc_ctrl:alias_expr_calc"]
    )


def test_if_expr_calc_are_disjunct(default_session):
    c1 = default_session.config.get("simu_expr_calc_ctrl")

    assert c1.constants.m == 10
    assert c1.constants.n == 100
    assert "p" not in dir(c1.constants)

    c2 = default_session.config.get("simu_expr_calc_ctrl2")

    # check that the import of the first couter does not influence the second one
    assert "p" not in dir(c1.constants)
    assert c1.constants.m == 10

    # check that the second counter is not influenced by the first one
    assert c2.constants.m == 20
    assert "n" not in dir(c2.constants)


def test_calc_counter_0D_1D_2D(default_session, lima_simulator):

    # 0d
    times2 = default_session.config.get("times2")
    s = loopscan(10, .1, times2)
    data = s.get_data()
    assert (
        data["times2:times2out"].shape
        == data["simulation_counter_controller:sim_ct_gauss"].shape
    )
    assert all(
        data["times2:times2out"]
        == data["simulation_counter_controller:sim_ct_gauss"] * 2
    )

    # 1d
    times2_1d = default_session.config.get("times2_1d")
    s = loopscan(10, .1, times2_1d, save=False)
    data = s.get_data()
    assert data["times2_1d:times2out_1d"].shape == data["simu1:spectrum_det0"].shape
    assert numpy.array_equal(
        data["times2_1d:times2out_1d"], data["simu1:spectrum_det0"] * 2
    )

    # 2d
    times2_2d = default_session.config.get("times2_2d")
    s = loopscan(10, 0.001, times2_2d, save=False)

    data = s.get_data()
    assert (
        data["times2_2d:times2out_2d"].shape
        == data["lima_simulator:image"].as_array().shape
    )
    assert numpy.array_equal(
        data["times2_2d:times2out_2d"], data["lima_simulator:image"].as_array() * 2
    )
