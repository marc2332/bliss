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
from bliss.scanning.scan import ScanDisplay
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.chain import AcquisitionChain
from bliss.controllers.lima.lima_base import Lima
from bliss.common.scans import DEFAULT_CHAIN
from bliss.common.scans import ascan
from bliss.common.measurement import CalcCounterController
from bliss.scanning.acquisition.calc import CalcHook


def scan_demo(motor, start, stop, npoints, count_time, *counters):

    total_time = count_time * npoints
    acq_master = SoftwarePositionTriggerMaster(
        motor, start, stop, npoints, time=total_time
    )

    chain = AcquisitionChain()
    builder = ChainBuilder(counters)

    scan_params = {"npoints": npoints, "count_time": count_time}
    lima_params = {
        "acq_nb_frames": npoints,
        "acq_expo_time": count_time * 0.5,
        "acq_mode": "SINGLE",
        "acq_trigger_mode": "INTERNAL_TRIGGER_MULTI",
        "acc_max_expo_time": 1.,
        "prepare_once": True,
        "start_once": False,
    }

    for node in builder.get_nodes_by_controller_type(Lima):
        node.set_parameters(scan_params=scan_params, acq_params=lima_params)
        for cnode in node.children:
            cnode.set_parameters(
                scan_params=scan_params, acq_params={"count_time": count_time}
            )

        chain.add(acq_master, node)

    # for node in builder.get_top_level_nodes():
    #     node.set_parameters(scan_params=scan_params)
    #     chain.add(acq_master, node)

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

    scan_demo(roby, 0, 1, 2, 0.1, simulator1, simulator2.counters.r2_sum)


def test_default_scan(default_session, lima_simulator):

    # --- make calc counters ------------------------

    # Mean caclulaion
    class Mean(CalcHook):
        def __init__(self, name="mean", cnt1_name="diode", cnt2_name="diode2"):
            self.name = name
            self.cnt1_name = cnt1_name
            self.cnt2_name = cnt2_name

        def prepare(self):
            self.data = {}

        def compute(self, sender, data_dict):
            # Gathering all needed data to calculate the mean
            # Datas of several counters are not emitted at the same time
            nb_point_to_emit = numpy.inf
            for cnt_name in (self.cnt1_name, self.cnt2_name):
                cnt_data = data_dict.get(cnt_name, [])
                data = self.data.get(cnt_name, [])
                if len(cnt_data):
                    data = numpy.append(data, cnt_data)
                    self.data[cnt_name] = data
                nb_point_to_emit = min(nb_point_to_emit, len(data))
            # Maybe noting to do
            if not nb_point_to_emit:
                return

            # Calculation
            mean_data = (
                self.data[self.cnt1_name][:nb_point_to_emit]
                + self.data[self.cnt2_name][:nb_point_to_emit]
            ) / 2.
            # Removing already computed raw datas
            self.data = {
                key: data[nb_point_to_emit:] for key, data in self.data.items()
            }
            # Return name musst be the same as the counter name:
            # **mean** in that case
            return {self.name: mean_data}

    diode1 = default_session.config.get("diode")
    diode2 = default_session.config.get("diode2")
    diode3 = default_session.config.get("diode3")
    diode4 = default_session.config.get("diode4")
    diode5 = default_session.config.get("diode5")
    diode6 = default_session.config.get("diode6")
    diode7 = default_session.config.get("diode7")

    cc6 = CalcCounterController("cc6", Mean("cc6", "diode", "diode2"), diode1, diode2)
    cc5 = CalcCounterController("cc5", Mean("cc5", "diode4", "diode5"), diode4, diode5)
    cc4 = CalcCounterController("cc4", Mean("cc4", "diode6", "diode7"), diode6, diode7)
    cc3 = CalcCounterController(
        "cc3", Mean("cc3", "cc6", "diode3"), cc6.counters[0], diode3
    )
    cc2 = CalcCounterController(
        "cc2", Mean("cc2", "cc5", "cc4"), cc5.counters[0], cc4.counters[0]
    )
    cc1 = CalcCounterController(
        "cc1", Mean("cc1", "cc3", "cc2"), cc3.counters[0], cc2.counters[0]
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
