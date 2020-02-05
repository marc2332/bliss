# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent

from bliss.common.scans import DEFAULT_CHAIN, loopscan
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.scanning.acquisition.mca import McaAcquisitionSlave
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning.acquisition.counter import IntegratingCounterAcquisitionSlave
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionMaster
from bliss.controllers.counter import CounterController


def test_default_chain_with_sampling_counter(beacon):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-diode
    """
    diode = beacon.get("diode")
    assert diode

    scan_pars = {"npoints": 10, "count_time": 0.1}

    chain = DEFAULT_CHAIN.get(scan_pars, [diode])
    timer = chain.timer

    assert timer.count_time == 0.1

    nodes = chain.nodes_list
    assert len(nodes) == 2
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], SamplingCounterAcquisitionSlave)

    assert nodes[1].count_time == timer.count_time


def test_default_chain_with_three_sampling_counters(beacon):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-diode2
        |-diode
        |-diode3

    diode2 and diode3 are from the same controller with 'read_all'
    """
    diode = beacon.get("diode")
    diode2 = beacon.get("diode2")
    diode3 = beacon.get("diode3")
    assert diode
    assert diode2
    assert diode3

    assert diode2._counter_controller == diode3._counter_controller

    scan_pars = {"npoints": 10, "count_time": 0.1}

    chain = DEFAULT_CHAIN.get(scan_pars, [diode2, diode, diode3])
    timer = chain.timer

    assert timer.count_time == 0.1

    nodes = chain.nodes_list
    assert len(nodes) == 3
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], SamplingCounterAcquisitionSlave)
    assert isinstance(nodes[2], SamplingCounterAcquisitionSlave)

    assert nodes[1].count_time == timer.count_time == nodes[2].count_time

    assert nodes[2] != nodes[1]

    counter_names = [c.fullname for c in nodes[1].channels]
    assert counter_names == ["simulation_diode_sampling_controller:diode"]
    # counters order is not important
    # as we use **set** to eliminate duplicated counters
    counter_names = set([c.fullname for c in nodes[2].channels])
    assert counter_names == set(
        [
            "simulation_diode_sampling_controller:diode2",
            "simulation_diode_sampling_controller:diode3",
        ]
    )


def test_default_chain_with_roi_counter(default_session, lima_simulator):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionMaster
          |
          |-roi1
    """
    lima_sim = default_session.config.get("lima_simulator")
    lima_sim.roi_counters["roi1"] = 0, 0, 10, 10
    assert lima_sim.counter_groups.roi1
    assert "roi1_sum" in lima_sim.counter_groups.roi_counters._fields

    try:
        scan_pars = {"npoints": 10, "count_time": 0.1}

        chain = DEFAULT_CHAIN.get(scan_pars, [lima_sim.counter_groups.roi1])
        timer = chain.timer

        assert timer.count_time == 0.1

        nodes = chain.nodes_list
        assert len(nodes) == 3
        assert isinstance(nodes[0], timer.__class__)
        assert isinstance(nodes[1], LimaAcquisitionMaster)
        assert isinstance(nodes[2], IntegratingCounterAcquisitionSlave)

        assert len(nodes[2].channels) == 5
        assert nodes[2].count_time == timer.count_time

        assert nodes[1].save_flag == False
    finally:
        lima_sim.roi_counters.clear()


def test_default_chain_ascan_with_roi_counter(default_session, lima_simulator):
    roby = default_session.config.get("roby")
    lima_sim = default_session.config.get("lima_simulator")
    lima_sim.roi_counters["roi1"] = 0, 0, 10, 10
    npoints = 2
    scan_pars = {"npoints": npoints, "count_time": 0.1}
    chain = DEFAULT_CHAIN.get(
        scan_pars, [lima_sim], top_master=LinearStepTriggerMaster(npoints, roby, 0, 0.1)
    )
    s = Scan(chain, scan_info=scan_pars, name="test_ascan", save=False)
    with gevent.Timeout(2):
        s.run()
    data = s.get_data()
    assert len(data["roi1_sum"]) == npoints


def test_default_chain_with_roicounter_and_diode(default_session, lima_simulator):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionMaster
          |
          |- roi1
        |
        |-diode
    """
    diode = default_session.config.get("diode")
    assert diode
    lima_sim = default_session.config.get("lima_simulator")
    lima_sim.roi_counters["roi1"] = (0, 0, 10, 10)
    assert lima_sim.roi_counters.has_key("roi1")
    assert lima_sim.counters.roi1_sum

    try:
        scan_pars = {"npoints": 10, "count_time": 0.1}

        chain = DEFAULT_CHAIN.get(scan_pars, [lima_sim.counter_groups.roi1, diode])
        timer = chain.timer

        assert timer.count_time == 0.1

        nodes = chain.nodes_list
        assert len(nodes) == 4
        assert isinstance(nodes[0], timer.__class__)
        assert isinstance(nodes[1], LimaAcquisitionMaster)
        assert isinstance(nodes[2], IntegratingCounterAcquisitionSlave)
        assert isinstance(nodes[3], SamplingCounterAcquisitionSlave)

        assert nodes[2].parent == nodes[1]
        assert nodes[3].parent == timer

        assert nodes[3].count_time == timer.count_time
        assert nodes[2].count_time == timer.count_time
    finally:
        lima_sim.roi_counters.clear()


def test_default_chain_with_roicounter_and_image(default_session, lima_simulator):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionMaster => saves image
          |
          |-roi1
    """
    lima_sim = default_session.config.get("lima_simulator")
    lima_sim.roi_counters["roi1"] = (0, 0, 10, 10)
    assert lima_sim.roi_counters.has_key("roi1")
    assert lima_sim.counters.roi1_sum

    try:
        scan_pars = {"npoints": 10, "count_time": 0.1, "save": True}

        chain = DEFAULT_CHAIN.get(scan_pars, [lima_sim.counter_groups.roi1, lima_sim])
        timer = chain.timer

        nodes = chain.nodes_list
        assert len(nodes) == 3
        assert isinstance(nodes[0], timer.__class__)
        assert isinstance(nodes[1], LimaAcquisitionMaster)
        assert isinstance(nodes[2], IntegratingCounterAcquisitionSlave)
        assert nodes[1].parent == timer
        assert nodes[2].parent == nodes[1]

        assert nodes[1].save_flag == True
    finally:
        lima_sim.roi_counters.clear()


def test_default_chain_with_lima_defaults_parameters(default_session, lima_simulator):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionMaster
          |
          |-roi1.avg
          |
          |-diode
    """
    diode = default_session.config.get("diode2")
    assert diode
    lima_sim = default_session.config.get("lima_simulator")
    lima_sim.roi_counters["roi1"] = (0, 0, 10, 10)
    assert lima_sim.roi_counters.has_key("roi1")
    assert lima_sim.counters.roi1_sum

    scan_pars = {"npoints": 10, "count_time": 0.1}

    try:
        DEFAULT_CHAIN.set_settings(
            [
                {"device": diode, "master": lima_sim},
                {
                    "device": lima_sim,
                    "acquisition_settings": {"acq_trigger_mode": "EXTERNAL_GATE"},
                },
            ]
        )

        chain = DEFAULT_CHAIN.get(scan_pars, [lima_sim.counters.roi1_avg, diode])
        timer = chain.timer

        nodes = chain.nodes_list
        assert len(nodes) == 4
        assert isinstance(nodes[0], timer.__class__)
        assert isinstance(nodes[1], LimaAcquisitionMaster)
        assert isinstance(nodes[2], IntegratingCounterAcquisitionSlave)
        assert isinstance(nodes[3], SamplingCounterAcquisitionSlave)

        assert nodes[2].parent == nodes[1]
        assert nodes[3].parent == nodes[1]
        assert nodes[1].parent == timer

        assert nodes[1].acq_params.get("acq_trigger_mode") == "EXTERNAL_GATE"
    finally:
        lima_sim.roi_counters.clear()
        DEFAULT_CHAIN.set_settings([])


def test_default_chain_with_recursive_master(default_session, lima_simulator):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-FakeMaster
           |
           |-LimaAcquisitionMaster
              |
              |-diode
    """
    lima_sim = default_session.config.get("lima_simulator")
    diode = default_session.config.get("diode2")
    assert diode

    scan_pars = {"npoints": 10, "count_time": 0.1}

    class FakeMaster(CounterController):
        def __init__(self, name):
            super().__init__(name)

        def get_acquisition_object(
            self, acq_params, ctrl_params=None, parent_acq_params=None
        ):
            return AcquisitionMaster(self, ctrl_params=ctrl_params, **acq_params)

        def get_default_chain_parameters(self, scan_params, acq_params):
            return acq_params

    fake_master = FakeMaster("fake")

    try:
        DEFAULT_CHAIN.set_settings(
            [
                {"device": diode, "master": lima_sim},
                {
                    "device": lima_sim,
                    "master": fake_master,
                    "acquisition_settings": {"acq_trigger_mode": "EXTERNAL_GATE"},
                },
            ]
        )

        chain = DEFAULT_CHAIN.get(scan_pars, [diode])
        timer = chain.timer

        nodes = chain.nodes_list
        assert len(nodes) == 4
        assert isinstance(nodes[0], timer.__class__)
        assert isinstance(nodes[1].device, FakeMaster)
        assert isinstance(nodes[2], LimaAcquisitionMaster)
        assert isinstance(nodes[3], SamplingCounterAcquisitionSlave)

        assert nodes[1].parent == timer
        assert nodes[2].parent == nodes[1]
        assert nodes[3].parent == nodes[2]

    finally:
        DEFAULT_CHAIN.set_settings([])


def test_default_chain_with_mca_defaults_parameters(default_session, lima_simulator):
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionMaster
          |
          |-mca
    """
    lima_sim = default_session.config.get("lima_simulator")
    mca = default_session.config.get("simu1")

    scan_pars = {"npoints": 10, "count_time": 0.1}

    try:
        DEFAULT_CHAIN.set_settings(
            [
                {
                    "device": mca,
                    "master": lima_sim,
                    "acquisition_settings": {"trigger_mode": "GATE"},
                }
            ]
        )

        chain = DEFAULT_CHAIN.get(scan_pars, [mca.counters.spectrum_det0])
        timer = chain.timer

        nodes = chain.nodes_list
        assert len(nodes) == 3
        assert isinstance(nodes[0], timer.__class__)
        assert isinstance(nodes[1], LimaAcquisitionMaster)
        assert isinstance(nodes[2], McaAcquisitionSlave)

        assert nodes[2].parent == nodes[1]
        assert nodes[1].parent == timer

        assert nodes[2].trigger_mode == McaAcquisitionSlave.GATE
    finally:
        DEFAULT_CHAIN.set_settings([])


# ~ def test_set_settings_with_ctrl_settings(session, lima_simulator, scan_tmpdir):
# ~ lima_sim = session.config.get("lima_simulator")
# ~ DEFAULT_CHAIN = session.env_dict["DEFAULT_CHAIN"]
# ~ try:
# ~ DEFAULT_CHAIN.set_settings(
# ~ [
# ~ {
# ~ "device": lima_sim,
# ~ "controller_settings": {
# ~ "saving_format": "HDF5",
# ~ "saving_suffix": ".h5",
# ~ },
# ~ }
# ~ ]
# ~ )

# ~ # put scan file in a tmp directory
# ~ session.scan_saving.base_path = str(scan_tmpdir)

# ~ s = loopscan(1, 0.01, lima_sim)

# ~ finally:
# ~ DEFAULT_CHAIN.set_settings([])

# ~ f = h5py.File(
# ~ os.path.join(
# ~ os.path.dirname(s.writer.filename), "scan0001", "lima_simulator_0000.h5"
# ~ ), mode="a"
# ~ )

# ~ assert f["entry_0000"]
