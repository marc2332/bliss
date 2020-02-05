# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import setup_globals
from bliss.scanning.chain import AcquisitionChain, ChainPreset, ChainIterationPreset
from bliss.scanning.scan import ScanPreset
from bliss.common import scans


def test_simple_preset(session):
    class SimplePreset(ChainPreset):
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
    scans.DEFAULT_CHAIN.add_preset(preset)

    simul_counter = getattr(setup_globals, "sim_ct_gauss")
    m1 = getattr(setup_globals, "m1")

    scans.ascan(m1, 0, 0.1, 2, 0, simul_counter, save=False)
    assert preset.prepare_called == 1
    assert preset.start_called == 1
    assert preset.stop_called == 1


def test_iteration_preset(session):
    class IterationPreset(ChainPreset):
        class Iteration(ChainIterationPreset):
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
            pass

        def get_iterator(self, chain):
            if not isinstance(chain, AcquisitionChain):
                raise ValueError("Expected an AcquisitionChain object")
            while True:
                yield self.Iteration(self)

    preset = IterationPreset()
    scans.DEFAULT_CHAIN.add_preset(preset)

    simul_counter = getattr(setup_globals, "sim_ct_gauss")
    m1 = getattr(setup_globals, "m1")

    scans.ascan(m1, 0, 0.1, 9, 0, simul_counter, save=False)
    assert preset.prepare_called == 10
    assert preset.start_called == 10
    assert preset.stop_called == 10


def test_scan_preset(session):
    class Preset(ScanPreset):
        def __init__(self):
            self.prepare_counter = 0
            self.start_counter = 0
            self.stop_counter = 0

        def prepare(self, scan):
            self.prepare_counter += 1

        def start(self, scan):
            self.start_counter += 1

        def stop(self, scan):
            self.stop_counter += 1

    preset = Preset()
    diode = session.config.get("diode")
    s = scans.loopscan(2, 0, diode, run=False)
    s.add_preset(preset)
    s.run()
    assert preset.prepare_counter == 1
    assert preset.start_counter == 1
    assert preset.stop_counter == 1
