# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
import glob
import os.path
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


def test_limatake(session, lima_simulator, lima_simulator2, capsys):
    lima_simulator = session.config.get("lima_simulator")
    lima_simulator2 = session.config.get("lima_simulator2")

    # --- without any device
    with pytest.raises(RuntimeError):
        limatake(0.01)

    # --- with active MG
    active_mg = session.env_dict["ACTIVE_MG"]
    active_mg.add(lima_simulator.image)

    s = limatake(0.01, nbframes=3)

    output = capsys.readouterr().out

    # check acq. chain is properly displayed in output
    #    assert output.startswith("acquisition chain\n└── lima_simulator\n")
    # check last frame number from output
    assert output.split()[-4].startswith("#3")

    assert s.get_data()[lima_simulator.image].get_image(2) is not None

    # --- with one lima device as argument and title set
    s = limatake(0.01, 1, lima_simulator, title="my_limatake")
    assert s.get_data()[lima_simulator.image].get_image(0) is not None
    assert s.scan_info["title"].startswith("my_limatake")

    # --- with two lima device as argument
    s = limatake(0.01, 1, lima_simulator, lima_simulator2)
    assert s.get_data()[lima_simulator.image].get_image(0) is not None
    assert s.get_data()[lima_simulator2.image].get_image(0) is not None

    # --- with acquisition/controller common parameters
    s = limatake(
        0.1, 2, lima_simulator, acq_mode="ACCUMULATION", acc_max_expo_time=0.05
    )
    assert lima_simulator._proxy.acq_mode == "ACCUMULATION"
    assert lima_simulator._proxy.acc_nb_frames == 2
    assert lima_simulator._proxy.acc_max_expo_time == 0.05

    # --- check saving
    scan_saving = session.scan_saving
    scan_saving_dump = scan_saving.to_dict()

    try:
        scan_saving.images_path_template = "{scan_name}_{scan_number}"
        scan_saving.images_prefix = "{img_acq_device}"
        scan_saving.scan_number_format = "%1d"
        scan_config = scan_saving.get()

        s = limatake(0.01, 1, lima_simulator, save=True)

        assert os.path.isdir(scan_config["root_path"])
        assert os.path.exists(
            os.path.join(scan_config["root_path"], "limatake_1/lima_simulator0000.edf")
        )
    finally:
        scan_saving.from_dict(scan_saving_dump)
