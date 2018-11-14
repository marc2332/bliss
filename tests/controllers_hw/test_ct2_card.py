# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest

from bliss.controllers.ct2 import card


class TestP201(unittest.TestCase):
    def setUp(self):
        self.p201 = card.P201Card()
        self.p201.set_interrupts()
        self.p201.reset()
        self.p201.software_reset()

    def tearDown(self):
        self.p201.set_interrupts()
        self.p201.reset()
        self.p201.software_reset()

    def test_clock(self):
        self.p201.set_clock(card.Clock.CLK_DISABLE)
        clock = self.p201.get_clock()
        self.assertEqual(clock, card.Clock.CLK_DISABLE)

        self.p201.set_clock(card.Clock.CLK_66_66_MHz)
        clock = self.p201.get_clock()
        self.assertEqual(clock, card.Clock.CLK_66_66_MHz)

    def test_output_level(self):
        for c in (
            {9: card.Level.DISABLE, 10: card.Level.DISABLE},
            {9: card.Level.TTL, 10: card.Level.NIM},
            {9: card.Level.NIM, 10: card.Level.TTL},
            {9: card.Level.TTL, 10: card.Level.TTL},
            {9: card.Level.NIM, 10: card.Level.NIM},
        ):
            self.p201.set_output_channels_level(c)
            r = self.p201.get_output_channels_level()
            self.assertEqual(c, r)

    def test_output_channels_level(self):
        for c in ({9: 0, 10: 0}, {9: 1, 10: 0}, {9: 0, 10: 1}, {9: 1, 10: 1}):
            self.p201.set_output_channels_software_enable(c)
            r = self.p201.get_output_channels_software_enable()
            self.assertEqual(c, r)

    def test_output_channels_source(self):
        srcs = (
            {9: card.OutputSrc.CLK_1_MHz, 10: card.OutputSrc.DISABLE},
            {9: card.OutputSrc.DISABLE, 10: card.OutputSrc.CH_1_RISING_FALLING},
            {9: card.OutputSrc.CT_6_START_STOP, 10: card.OutputSrc.CT_8_SWITCH},
        )
        for src in srcs:
            self.p201.set_output_channels_source(src)
            result = self.p201.get_output_channels_source()
            self.assertEqual(src, result)

    def test_output_channels_filter(self):
        filters = (
            {
                9: card.FilterOutput(
                    clock=card.FilterClock.CLK_12_5_MHz, enable=True, polarity=0
                ),
                10: card.FilterOutput(
                    clock=card.FilterClock.CLK_10_KHz, enable=False, polarity=1
                ),
            },
        )
        for filter in filters:
            self.p201.set_output_channels_filter(filter)
            result = self.p201.get_output_channels_filter()
            self.assertEqual(filter, result)

    def test_channels_interrupts(self):
        triggers = {
            1: card.TriggerInterrupt(rising=True),
            5: card.TriggerInterrupt(falling=True),
            10: card.TriggerInterrupt(rising=True, falling=True),
        }

        self.p201.set_channels_interrupts(triggers)
        for ch in (2, 3, 4, 6, 7, 8, 9):
            triggers[ch] = card.TriggerInterrupt()
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
        input = {1: set((10,)), 2: set((3, 4, 5)), 5: set((5, 6, 7))}

        expected_ret = {
            "A": (1 << (10 - 1))
            | ((1 << (3 - 1) | 1 << (4 - 1) | 1 << (5 - 1)) << 16),  # counter 2
            "B": 0,
            "C": 1 << (5 - 1) | 1 << (6 - 1) | 1 << (7 - 1),
            "D": 0,
            "E": 0,
            "F": 0,
        }

        ret = self.p201.set_counters_latch_sources(input)
        self.assertEqual(ret, expected_ret)

        expected_output = dict(input)
        for i in [3, 4] + list(range(6, 13)):
            expected_output[i] = set()

        output = self.p201.get_counters_latch_sources()
        self.assertEqual(output, expected_output)


if __name__ == "__main__":
    unittest.main()
