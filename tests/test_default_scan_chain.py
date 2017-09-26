# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.scanning.chain import AcquisitionChain
from bliss.common.scans import default_chain
from bliss.scanning.acquisition.lima import LimaAcquisitionDevice
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice, IntegratingCounterAcquisitionDevice 
from bliss.controllers.simulation_diode import CONTROLLER as diode23_controller


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

    scan_pars = { "npoints": 10,
                  "count_time": 0.1 }

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_pars, [diode])

    assert timer.count_time == 0.1

    nodes = chain.nodes_list
    assert len(nodes) == 2
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], SamplingCounterAcquisitionDevice)

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

    #assert diode.controller is None
    #assert diode2.controller == diode3.controller == diode23_controller

    scan_pars = { "npoints": 10,
                  "count_time": 0.1 }

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_pars, [diode2, diode, diode3])

    assert timer.count_time == 0.1

    nodes = chain.nodes_list
    assert len(nodes) == 3
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], SamplingCounterAcquisitionDevice)
    assert isinstance(nodes[2], SamplingCounterAcquisitionDevice)

    assert nodes[1].count_time == timer.count_time == nodes[2].count_time

    assert nodes[2] != nodes[1]
    
    assert nodes[1].counter_names == ['diode']
    # counters order is not important
    # as we use **set** to eliminate duplicated counters
    assert set(nodes[2].counter_names) == set(['diode2', 'diode3'])

def test_default_chain_with_bpm(beacon):
    pytest.xfail()
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionDevice
          |
          |-X
          |-Y
          |-intensity
    """
    lima_sim = beacon.get("lima_simulator")
    assert lima_sim.bpm.x
    assert lima_sim.bpm.y
    assert lima_sim.bpm.intensity

    scan_pars = { "npoints": 10,
                  "count_time": 0.1 }

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_pars, [lima_sim.bpm.x, lima_sim.bpm.y, lima_sim.bpm.intensity])
    
    assert timer.count_time == 0.1

    nodes = chain.nodes_list
    assert len(nodes) == 3 
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], LimaAcquisitionDevice)
    assert isinstance(nodes[2], IntegratingCounterAcquisitionDevice)

    assert len(nodes[2].counter_names) == 3
    assert nodes[2].count_time == timer.count_time

    assert nodes[1].save_flag == False

def test_default_chain_with_bpm_and_diode(beacon):
    pytest.xfail()
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionDevice
          |
          |-intensity
        |
        |-diode
    """
    lima_sim = beacon.get("lima_simulator")
    diode = beacon.get("diode")
    assert lima_sim.bpm.intensity
    assert diode

    scan_pars = { "npoints": 10,
                  "count_time": 0.1 }

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_pars, [lima_sim.bpm.intensity, diode])

    assert timer.count_time == 0.1

    nodes = chain.nodes_list
    assert len(nodes) == 4
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], LimaAcquisitionDevice)
    assert isinstance(nodes[2], IntegratingCounterAcquisitionDevice)
    assert isinstance(nodes[3], SamplingCounterAcquisitionDevice)

    assert nodes[2].parent == nodes[1]
    assert nodes[3].parent == timer

    assert nodes[2].count_time == timer.count_time
    assert nodes[3].count_time == nodes[2].count_time


def test_default_chain_with_bpm_and_image(beacon):
    pytest.xfail()
    """Want to build the following acquisition chain:

    root
      |
      |-Timer
        |
        |-LimaAcquisitionDevice => saves image
          |
          |-X
    """

    lima_sim = beacon.get("lima_simulator")

    scan_pars = { "npoints": 10,
                  "count_time": 0.1,
                  "save": True,
              }

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_pars, [lima_sim.bpm.x, lima_sim])
   
    nodes = chain.nodes_list
    assert len(nodes) == 3
    assert isinstance(nodes[0], timer.__class__)
    assert isinstance(nodes[1], LimaAcquisitionDevice)
    assert isinstance(nodes[2], IntegratingCounterAcquisitionDevice)
    assert nodes[1].parent == timer
    assert nodes[2].parent == nodes[1]

    assert nodes[1].save_flag == True
