# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
CT2 pure software tests (no hardware required)
"""

from bliss.controllers.ct2.card import CtConfig, CtClockSrc, CtGateSrc
from bliss.controllers.ct2.card import CtHardStartSrc, CtHardStopSrc


def test_ctconfig_empty():
    cfg = CtConfig()
    assert CtConfig.toint(cfg) == 0


def test_ctconfig_init_with_1_param():
    clock_1_mhz = 0x03
    assert clock_1_mhz == CtClockSrc.CLK_1_MHz.value

    cfg = CtConfig(clock_source=CtClockSrc.CLK_1_MHz)

    assert CtConfig.toint(cfg) == CtClockSrc.CLK_1_MHz.value
    assert cfg["clock_source"] == CtClockSrc.CLK_1_MHz


def test_ctconfig_init_with_params():
    reg = 0x04 | (0x1E << 7) | (0x09 << 13) | (0x52 << 20) | (1 << 30) | (0 << 31)

    cfg = CtConfig(
        clock_source=CtClockSrc.CLK_12_5_MHz,
        gate_source=CtGateSrc.CT_6_GATE_ENVELOP,
        hard_start_source=CtHardStartSrc.CH_9_RISING_EDGE,
        hard_stop_source=CtHardStopSrc.CT_10_EQ_CMP_10,
        reset_from_hard_soft_stop=True,
        stop_from_hard_stop=False,
    )

    assert CtConfig.toint(cfg) == reg
    assert cfg["clock_source"] == CtClockSrc.CLK_12_5_MHz
    assert cfg["gate_source"] == CtGateSrc.CT_6_GATE_ENVELOP
    assert cfg["hard_start_source"] == CtHardStartSrc.CH_9_RISING_EDGE
    assert cfg["hard_stop_source"] == CtHardStopSrc.CT_10_EQ_CMP_10
    assert cfg["reset_from_hard_soft_stop"]
    assert not cfg["stop_from_hard_stop"]


def test_ctconfig_set():
    cfg = CtConfig()

    cfg["clock_source"] = CtClockSrc.CLK_10_KHz
    reg = 0x1
    assert cfg["clock_source"] == CtClockSrc.CLK_10_KHz
    assert CtConfig.toint(cfg) == CtClockSrc.CLK_10_KHz.value
    assert CtConfig.toint(cfg) == reg

    cfg["hard_start_source"] = CtHardStartSrc.CT_6_START_STOP
    reg = 0x1 | (0x42 << 13)
    assert cfg["clock_source"] == CtClockSrc.CLK_10_KHz

    assert cfg["hard_start_source"] == CtHardStartSrc.CT_6_START_STOP
    assert CtConfig.toint(cfg) == reg
