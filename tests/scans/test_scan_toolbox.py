# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

# ----------------------------- TEST -----------------------------------------------------------
import numpy
from bliss.scanning.toolbox import ChainBuilder
from bliss.controllers.lima.roi import Roi
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.chain import AcquisitionChain
from bliss.controllers.lima.lima_base import Lima
from bliss.common.scans import DEFAULT_CHAIN
from bliss.common.scans import ascan
from bliss.controllers.simulation_calc_counter import MeanCalcCounterController


# ---- TEST THE DEFAULT CHAIN -------------------------------
def test_default_scan(default_session, lima_simulator):

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
    # ------- import lima_simulator ------------------

    simulator1 = default_session.config.get("lima_simulator")  # controller lima

    r1 = Roi(0, 0, 100, 200)

    simulator1.roi_counters["r1"] = r1

    # ------------------------------------------------

    roby = default_session.config.get("roby")

    DEFAULT_CHAIN.set_settings(
        [
            {"device": diode1, "master": simulator1},
            {
                "device": simulator1,
                "acquisition_settings": {"acq_trigger_mode": "INTERNAL_TRIGGER_MULTI"},
            },
        ]
    )

    sc = ascan(roby, 0, 10, 10, 0.1, cc1, simulator1)

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


# ---- TEST CONTINOUS SCANS AND USER DEFINED SCANS -------------------------------
def scan_demo_all_acq_pars(motor, start, stop, npoints, count_time, *counters):
    """ Case where all masters and slaves acq_params are provided """

    acq_master = LinearStepTriggerMaster(npoints, motor, start, stop)

    chain = AcquisitionChain()
    builder = ChainBuilder(counters)

    lima_params = {
        "acq_nb_frames": npoints,
        "acq_expo_time": count_time * 0.5,
        "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI",
        "wait_frame_id": range(npoints),
        "prepare_once": True,
        "start_once": False,
        "stat_history": npoints,
    }

    lima_children_params = {"count_time": count_time}

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(acq_params=lima_params)

        for cnode in node.children:
            cnode.set_parameters(acq_params=lima_children_params)

        chain.add(acq_master, node)

    builder.print_tree(not_ready_only=False)

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
        data_watch_callback=StepScanDataWatch(),
    )

    sc.run()


def scan_demo_only_master_acq_pars(motor, start, stop, npoints, count_time, *counters):
    """ Case where all masters acq_params are provided but slaves acq_params are not given.
        In that case the slaves will try to find their acq_params from the acq_params of their master.
    """
    acq_master = LinearStepTriggerMaster(npoints, motor, start, stop)

    chain = AcquisitionChain()
    builder = ChainBuilder(counters)

    lima_params = {
        "acq_nb_frames": npoints,
        "acq_expo_time": count_time * 0.5,
        "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI",
        "wait_frame_id": range(npoints),
        "prepare_once": True,
        "start_once": False,
        "stat_history": npoints,
    }

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(acq_params=lima_params)

        chain.add(acq_master, node)

    builder.print_tree(not_ready_only=False)

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
        data_watch_callback=StepScanDataWatch(),
    )

    sc.run()


def scan_demo_partial_acq_pars(motor, start, stop, npoints, count_time, *counters):
    """ Case where only some master acq_params are provided """

    acq_master = LinearStepTriggerMaster(npoints, motor, start, stop)

    chain = AcquisitionChain()
    builder = ChainBuilder(counters)

    lima_params = {
        "acq_nb_frames": npoints,
        "acq_expo_time": count_time * 0.5,
        # "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI",
        "prepare_once": True,
        "start_once": False,
    }

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(acq_params=lima_params)

        chain.add(acq_master, node)

    builder.print_tree(not_ready_only=False)

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
        data_watch_callback=StepScanDataWatch(),
    )

    sc.run()


def scan_demo_missing_acq_pars(motor, start, stop, npoints, count_time, *counters):
    """ Case where some mandatory master acq_params are missing """

    acq_master = LinearStepTriggerMaster(npoints, motor, start, stop)

    chain = AcquisitionChain()
    builder = ChainBuilder(counters)

    lima_params = {
        "acq_nb_frames": npoints,
        # "acq_expo_time": count_time * 0.5,
        # "acq_mode": "SINGLE",
        # "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI",
        # "prepare_once": True,
        # "start_once": False,
    }

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(acq_params=lima_params)

        chain.add(acq_master, node)

    builder.print_tree(not_ready_only=False)

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
        data_watch_callback=StepScanDataWatch(),
    )

    sc.run()


def test_continous_scan(default_session, lima_simulator, lima_simulator2):

    # ScanDisplay().auto=True

    simulator1 = default_session.config.get("lima_simulator")  # controller lima
    simulator2 = default_session.config.get("lima_simulator2")  # controller lima

    r1 = Roi(0, 0, 100, 200)
    r2 = Roi(10, 20, 200, 500)

    simulator1.roi_counters["r1"] = r1
    simulator2.roi_counters["r2"] = r2

    # ------------------------------------------------

    roby = default_session.config.get("roby")

    #  simulator.counters.r1_sum
    #  simulator.counters.r1_avg
    #  simulator.counters.r1_std
    #  simulator.counters.r1_min
    #  simulator.counters.r1_max

    # nodes = scan_demo(roby, 0, 10, 11, 1, simulator1.counters.r1_sum )
    # nodes = scan_demo(roby, 0, 10, 11, 1, simulator1.counter_groups.r1 )

    scan_demo_all_acq_pars(roby, 0, 1, 2, 0.01, simulator1, simulator2.counters.r2_sum)

    scan_demo_only_master_acq_pars(
        roby, 0, 1, 2, 0.01, simulator1, simulator2.counters.r2_sum
    )

    scan_demo_partial_acq_pars(
        roby, 0, 1, 2, 0.01, simulator1, simulator2.counters.r2_sum
    )

    try:
        scan_demo_missing_acq_pars(
            roby, 0, 1, 2, 0.01, simulator1, simulator2.counters.r2_sum
        )

    except Exception as e:
        print("scan_demo_missing_acq_pars: " + str(e))

        assert (
            str(e).strip()
            == "{'acq_params': [{'count_time': ['null value not allowed']}]}"
        )
