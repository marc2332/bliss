# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# ----------------------------- TEST -----------------------------------------------------------
import numpy

from bliss.common.scans import ascan
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

    # calc_chan_out = AcquisitionChannel("position", numpy.float, ())
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

    calc_chan_out = AcquisitionChannel("mean_pos", numpy.float, ())
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
