# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_lima_debug(session, lima_simulator):
    simulator = session.config.get("lima_simulator")

    simdebug = simulator.debug

    # -- global on/off
    simdebug.on()
    output = simdebug.__info__()
    assert output.count("ON") == 11 + 8
    assert output.count("OFF") == 0

    simdebug.off()
    output = simdebug.__info__()
    assert output.count("ON") == 0 + 1
    assert output.count("OFF") == 11 + 7

    # -- modules debug
    modules = simdebug.modules
    modules.set("control", "camera")
    output = modules.__info__()
    assert output.count("ON") == 2

    modules.on("common")
    output = modules.__info__()
    assert output.count("ON") == 3
    attr = simulator.proxy.debug_modules
    assert attr == ("Common", "Control", "Camera")

    modules.off("camera")
    output = modules.__info__()
    assert output.count("OFF") == 9
    attr = simulator.proxy.debug_modules
    assert attr == ("Common", "Control")

    # -- types debug
    types = simdebug.types
    types.off()
    output = types.__info__()
    assert output.count("ON") == 1

    types.on("warning", "error")
    output = types.__info__()
    assert output.count("ON") == 3

    attr = simulator.proxy.debug_types
    assert attr == ("Fatal", "Error", "Warning")
