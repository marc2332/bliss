# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import setup_globals
from bliss.common.standard import wa, wm, sta, stm


def test_wa_normal(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = False
    wa()
    captured = capsys.readouterr()
    output = "Current Positions (user, dial)\n"
    output += "\n"
    output += "    bad\n"
    output += "-------\n"
    output += "0.00000\n"
    output += "0.00000\n"

    assert captured.out == output


def test_wa_exception(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = True
    wa()
    captured = capsys.readouterr()

    output = "Current Positions (user, dial)\n"
    output += "\n"
    output += "bad\n"
    output += "-----\n"
    output += "!ERR\n"
    output += "!ERR\n"
    output += "\n"
    output += "========= WARNING: Motor 'bad' has failed with error: ==============\n"
    output += "\n"
    output += "Traceback (most recent call last):\n"

    outputend = "RuntimeError: BAD POSITION\n"
    outputend += "\n"
    outputend += "\n"

    assert captured.out[: len(output)] == output
    assert captured.out[-len(outputend) :] == outputend


def test_wm_normal(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = False
    wm("bad")
    captured = capsys.readouterr()

    output = "\n"
    output += "             bad\n"
    output += "-------  -------\n"
    output += "User\n"
    output += "High         inf\n"
    output += "Current  0.00000\n"
    output += "Low         -inf\n"
    output += "Dial\n"
    output += "High         inf\n"
    output += "Current  0.00000\n"
    output += "Low         -inf\n"

    assert captured.out == output


def test_wm_exception(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = True
    wm("bad")
    captured = capsys.readouterr()

    output = "\n"
    output += "         bad\n"
    output += "-------  -----\n"
    output += "User\n"
    output += "High     inf\n"
    output += "Current  !ERR\n"
    output += "Low      -inf\n"
    output += "Dial\n"
    output += "High     inf\n"
    output += "Current  !ERR\n"
    output += "Low      -inf\n"
    output += "\n"
    output += "========= WARNING: Motor 'bad' has failed with error: ==============\n"
    output += "\n"
    output += "Traceback (most recent call last):\n"

    outputend = "RuntimeError: BAD POSITION\n"
    outputend += "\n"
    outputend += "\n"

    assert captured.out[: len(output)] == output
    assert captured.out[-len(outputend) :] == outputend


def test_sta_normal(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = False
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_sta_exception(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = True
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"
    output += "\n"
    output += "========= WARNING: Motor 'bad' has failed with error: ==============\n"
    output += "\n"
    output += "Traceback (most recent call last):\n"

    outputend = "RuntimeError: BAD POSITION\n"
    outputend += "\n"
    outputend += "\n"

    assert captured.out[: len(output)] == output
    assert captured.out[-len(outputend) :] == outputend


def test_stm_normal(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = False
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_stm_exception(beacon, capsys):
    bad = beacon.get("bad")
    setattr(setup_globals, "bad", bad)
    bad.controller.bad_position = True
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"
    output += "\n"
    output += "========= WARNING: Motor 'bad' has failed with error: ==============\n"
    output += "\n"
    output += "Traceback (most recent call last):\n"

    outputend = "RuntimeError: BAD POSITION\n"
    outputend += "\n"
    outputend += "\n"

    assert captured.out[: len(output)] == output
    assert captured.out[-len(outputend) :] == outputend