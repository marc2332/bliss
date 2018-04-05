# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import setup_globals
from bliss.scanning.chain import AcquisitionChain, Preset
from bliss.scanning.standard import default_chain_add_preset
from bliss.common import scans

def test_simple_preset(beacon):
    session = beacon.get("test_session")
    session.setup()
    class SimplePreset(Preset):
        def __init__(self):
            self.prepare_called = 0
            self.start_called = 0
            self.stop_called = 0
            
        def prepare(self, chain):
            if not isinstance(chain, AcquisitionChain):
                raise ValueError("Expected an AcquisitionChain object")
            self.prepare_called += 1

        def start(self, chain):
            if not isinstance(chain, AcquisitionChain):
                raise ValueError("Expected an AcquisitionChain object")
            self.start_called += 1

        def stop(self, chain):
            if not isinstance(chain, AcquisitionChain):
                raise ValueError("Expected an AcquisitionChain object")
            self.stop_called += 1

    preset = SimplePreset()
    default_chain_add_preset(preset)
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    m1 = getattr(setup_globals, 'm1')
    counter = counter_class("gaussian", 10, cnt_time=0)
    scans.ascan(m1, 0, 0.1, 2, 0, counter, save=False)
    assert preset.prepare_called == 1
    assert preset.start_called == 1
    assert preset.stop_called == 1

def test_iteration_preset(beacon):
    session = beacon.get("test_session")
    session.setup()
    class IterationPreset(Preset):
        class Iteration(Preset.Iteration):
            def __init__(self, cnt):
                self._cnt = cnt
            def prepare(self):
                self._cnt.prepare_called += 1
            def start(self):
                self._cnt.start_called += 1
            def stop(self):
                self._cnt.stop_called += 1

        def __init__(self):
            self.prepare_called = 0
            self.start_called = 0
            self.stop_called = 0
            
        def prepare(self, chain):
            if not isinstance(chain, AcquisitionChain):
                raise ValueError("Expected an AcquisitionChain object")
            while True:
                yield self.Iteration(self)


    preset = IterationPreset()
    default_chain_add_preset(preset)
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    m1 = getattr(setup_globals, 'm1')
    counter = counter_class("gaussian", 10, cnt_time=0)
    scans.ascan(m1, 0, 0.1, 10, 0, counter, save=False)
    assert preset.prepare_called == 10
    assert preset.start_called == 10
    assert preset.stop_called == 10
    

