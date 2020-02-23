# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
import glob
from bliss.common.scans import loopscan, DEFAULT_CHAIN
from bliss.shell.standard import limastat, limatake


def test_limastat(session, lima_simulator, capsys):
    simulator = session.config.get("lima_simulator")

    with pytest.raises(RuntimeError):
        limastat()

    limastat(simulator)

    output = capsys.readouterr().out
    assert (
        output
        == "\n        camera    history     incoming    compression    compression        write\n                     size        speed          ratio          speed        speed\n--------------  ---------  -----------  -------------  -------------  -----------\n\x1b[1mlima_simulator\x1b[0m         16  0.00 MB/sec              0    0.00 MB/sec  0.00 MB/sec\n\n"
    )

    active_mg = session.env_dict["ACTIVE_MG"]
    active_mg.add(simulator.image)

    limastat()

    output2 = capsys.readouterr().out
    assert output2 == output


def test_limatake(session, lima_simulator, capsys):
    simulator = session.config.get("lima_simulator")

    with pytest.raises(RuntimeError):
        limatake(0.01)

    active_mg = session.env_dict["ACTIVE_MG"]
    active_mg.add(simulator.image)

    s = limatake(0.01, nbframes=3)

    output = capsys.readouterr().out

    # check acq. chain is properly displayed in output
    assert output.startswith("acquisition chain\n└── lima_simulator\n")
    # check last frame number from output
    assert output.split()[-4].startswith("#3")

    assert s.get_data()[simulator.image].get_image(2) is not None
