# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
from bliss.shell.standard import wa, wm, wid, info


def test_undulator(beacon, dummy_tango_server):
    u23a = beacon.get("u23a")

    # u23a is form ESRF_Undulator class
    # not a tang_attr_as_counter => no format control
    assert u23a.position == 1.4078913

    assert u23a.velocity == 5

    assert u23a.acceleration == 125


def test_undulator_disabled(default_session, dummy_tango_server, capsys):
    _, und_dev = dummy_tango_server
    u23a = default_session.config.get("u23a")

    und_dev.setDisabled(True)

    assert "DISABLED" in u23a.state

    wa()

    wa_output = capsys.readouterr().out

    assert "*DIS*" in wa_output

    wm(u23a)

    assert "u23a *DISABLED*" in capsys.readouterr().out

    info(u23a)


def test_wid(default_session, dummy_tango_server, capsys):
    _, und_dev = dummy_tango_server
    u23a = default_session.config.get("u23a")

    wid()

    wid_output = capsys.readouterr().out

    assert (
        wid_output
        == "\n    ---------------------------------------\n    ID Device Server id00/tango/dummy\n            Power: 0.000 /  0.0  KW\n    Power density: 0.000 / 0.0  KW/mr2\n\n    u23a - GAP:1.408 - ENABLED   \n\n"
    )

    und_dev.setDisabled(True)

    wid()

    assert "DISABLED" in capsys.readouterr().out
