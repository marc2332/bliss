# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest

from bliss.controllers import ct2


class TestCtConfig(unittest.TestCase):

    def test_ctconfig_empty(self):
        cfg = ct2.CtConfig()
        self.assertEqual(cfg.value, 0)

    def test_ctconfig_init_with_1_param(self):
        clock_1_mhz = 0x03
        self.assertEqual(clock_1_mhz, ct2.CtClockSrc.CLK_1_MHz.value)

        cfg = ct2.CtConfig(clock_source=ct2.CtClockSrc.CLK_1_MHz)

        self.assertEqual(cfg.value, ct2.CtClockSrc.CLK_1_MHz.value)
        self.assertEqual(cfg.clock_source, ct2.CtClockSrc.CLK_1_MHz)

    def test_ctconfig_init_with_params(self):
        reg = 0x04 | (0x1E << 7) | (0x09 << 13) | (0x52 << 20) | (1 << 30) | (0 << 31)

        cfg = ct2.CtConfig(clock_source=ct2.CtClockSrc.CLK_12_5_MHz,
                           gate_source=ct2.CtGateSrc.CT_6_GATE_ENVELOP,
                           hard_start_source=ct2.CtHardStartSrc.CH_9_RISING_EDGE,
                           hard_stop_source=ct2.CtHardStopSrc.CT_10_EQ_CMP_10,
                           reset_from_hard_soft_stop=True, 
                           stop_from_hard_stop=False)

        self.assertEqual(cfg.value, reg)
        self.assertEqual(cfg.clock_source, ct2.CtClockSrc.CLK_12_5_MHz)
        self.assertEqual(cfg.gate_source, ct2.CtGateSrc.CT_6_GATE_ENVELOP)
        self.assertEqual(cfg.hard_start_source, ct2.CtHardStartSrc.CH_9_RISING_EDGE)
        self.assertEqual(cfg.hard_stop_source, ct2.CtHardStopSrc.CT_10_EQ_CMP_10)
        self.assertTrue(cfg.reset_from_hard_soft_stop)
        self.assertFalse(cfg.stop_from_hard_stop)

    def test_ctconfig_set(self):
        cfg = ct2.CtConfig()
        self.assertEqual(cfg.value, 0)
        
        cfg['clock_source'] = ct2.CtClockSrc.CLK_10_KHz
        reg = 0x1
        self.assertEqual(cfg.clock_source, ct2.CtClockSrc.CLK_10_KHz)
        self.assertEqual(cfg['clock_source'], ct2.CtClockSrc.CLK_10_KHz)
        self.assertEqual(cfg.value, ct2.CtClockSrc.CLK_10_KHz.value)
        self.assertEqual(cfg.value, reg)

        cfg['hard_start_source'] = ct2.CtHardStartSrc.CT_6_START_STOP
        reg = 0x1 | (0x42 << 13)
        self.assertEqual(cfg.clock_source, ct2.CtClockSrc.CLK_10_KHz)
        self.assertEqual(cfg['clock_source'], ct2.CtClockSrc.CLK_10_KHz)

        self.assertEqual(cfg.hard_start_source, ct2.CtHardStartSrc.CT_6_START_STOP)
        self.assertEqual(cfg['hard_start_source'], ct2.CtHardStartSrc.CT_6_START_STOP)
        self.assertEqual(cfg.value, reg)


class TestP201(unittest.TestCase):

    def setUp(self):
        self.p201 = ct2.P201Card()
        self.p201.set_interrupts()
        self.p201.reset()
        self.p201.software_reset()

    def tearDown(self):
        self.p201.set_interrupts()
        self.p201.reset()
        self.p201.software_reset()

    def test_clock(self):
        self.p201.set_clock(ct2.Clock.CLK_DISABLE)
        clock = self.p201.get_clock()
        self.assertEqual(clock, ct2.Clock.CLK_DISABLE)

        self.p201.set_clock(ct2.Clock.CLK_66_66_MHz)
        clock = self.p201.get_clock()
        self.assertEqual(clock, ct2.Clock.CLK_66_66_MHz)

    def test_output_level(self):
        for c in ({9: ct2.Level.DISABLE,
                   10: ct2.Level.DISABLE },
                  {9: ct2.Level.TTL,
                   10: ct2.Level.NIM },
                  {9: ct2.Level.NIM,
                   10: ct2.Level.TTL },
                  {9: ct2.Level.TTL,
                   10: ct2.Level.TTL },
                  {9: ct2.Level.NIM,
                   10: ct2.Level.NIM },):
            self.p201.set_output_channels_level(c)
            r = self.p201.get_output_channels_level()
            self.assertEqual(c, r)
                  
    def test_output_channels_level(self):
        for c in ({9:0, 10:0}, {9:1, 10:0}, {9:0, 10:1}, {9:1, 10:1}):
            self.p201.set_output_channels_software_enable(c)
            r = self.p201.get_output_channels_software_enable()
            self.assertEqual(c, r)

    def test_output_channels_source(self):
        srcs = ({9: ct2.OutputSrc.CLK_1_MHz,
                 10: ct2.OutputSrc.DISABLE },
                {9: ct2.OutputSrc.DISABLE,
                 10: ct2.OutputSrc.CH_1_RISING_FALLING },
                {9: ct2.OutputSrc.CT_6_START_STOP,
                 10: ct2.OutputSrc.CT_8_SWITCH })
        for src in srcs:
            self.p201.set_output_channels_source(src)
            result = self.p201.get_output_channels_source()
            self.assertEqual(src, result)

    def test_output_channels_filter(self):
        filters = ({ 9: ct2.FilterOutput(clock=ct2.FilterClock.CLK_12_5_MHz,
                                         enable=True, polarity=0),
                     10: ct2.FilterOutput(clock=ct2.FilterClock.CLK_10_KHz,
                                          enable=False, polarity=1),},)
        for filter in filters:
            self.p201.set_output_channels_filter(filter)
            result = self.p201.get_output_channels_filter()
            self.assertEqual(filter, result)

    def test_channels_interrupts(self):
        triggers = { 1: ct2.TriggerInterrupt(rising=True), 
                     5: ct2.TriggerInterrupt(falling=True), 
                     10: ct2.TriggerInterrupt(rising=True, falling=True), }
        
        self.p201.set_channels_interrupts(triggers)
        for ch in (2,3,4,6,7,8,9):
            triggers[ch] = ct2.TriggerInterrupt()
        result = self.p201.get_channels_interrupts()
        
        
        self.assertEqual(triggers, result)

    def test_50ohm_adapter(self):
        # enable odd channels; disable even ones
        channels = {}
        for i in range(1, 11):
            channels[i] = i % 2 != 0
        
        self.p201.set_input_channels_50ohm_adapter(channels)

        result = self.p201.get_input_channels_50ohm_adapter()
        self.assertEqual(result, channels)

    def test_p201_counters_latch_sources(self):
        input = { 1: set((10,)), 
                  2: set((3, 4, 5)),
                  5: set((5, 6, 7))}
        
        expected_ret = {
            "A": (1<<(10-1)) | \
                 ( ( 1<<(3-1) | 1<<(4-1) | 1<<(5-1) ) << 16 ), # counter 2
            "B": 0,
            "C": 1<<(5-1) | 1<<(6-1) | 1<<(7-1),
            "D": 0,
            "E": 0,
            "F": 0,
        }

        ret = self.p201.set_counters_latch_sources(input)
        self.assertEqual(ret, expected_ret)

        expected_output = dict(input)
        for i in [3, 4] + range(6, 13):
            expected_output[i] = set()

        output = self.p201.get_counters_latch_sources()
        self.assertEqual(output, expected_output)
           
        
if __name__ == "__main__":
    unittest.main()
