# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import sys

from bliss.data import start_listener
from bliss.common import scans

import gevent
import pytest

# from bliss.shell.cli import repl
# repl.ERROR_REPORT.expert_mode = True


# @pytest.fixture
# def scan_listener(session):
#    #exit_read_fd, exit_write_fd = os.pipe()
#    listener = gevent.spawn(start_listener.main, "test_session" ) #exit_read_fd
#    yield listener
#    #os.write(exit_write_fd, b'!')
#    #listener.join()
#    listener.kill()
#    #os.close(exit_read_fd)
#    #os.close(exit_write_fd)


def test_scan_display(session, capsys):  # scan_listener

    listener = gevent.spawn(start_listener.main, "test_session")

    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")

    s = scans.a2scan(robz, 0, 9, roby, 10, 19, 10, 0.01, diode4, diode5)

    # gevent.sleep(1)
    captured = capsys.readouterr()

    # line 0 ===================================== Bliss session 'test_session': watching scans =====================================
    # line 1
    # line 2 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
    # line 3
    # line 4 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
    # line 5 a2scan robz 0 9 roby 10 19 10 0.01
    # line 6
    # line 7             #         dt[s]      robz[mm]          roby        diode4        diode5
    # line 8             0             0             0            10             4             5
    # line 9             1      0.167275             1            11             4             5
    # line 10            2      0.364229             2            12             4             5
    # line 11            3      0.562693             3            13             4             5
    # line 12            4      0.727321             4            14             4             5
    # line 13            5        0.8995             5            15             4             5
    # line 14            6        1.0627             6            16             4             5
    # line 15            7       1.22539             7            17             4             5
    # line 16            8       1.38847             8            18             4             5
    # line 17            9       1.55273             9            19             4             5
    # line 18

    lines = captured.out.split("\n")

    assert (
        lines[7].strip()
        == "#         dt[s]      robz[mm]          roby        diode4        diode5"
    )

    arry = []
    for line in lines[8:]:
        line = " ".join(line.strip().split())
        tab = line.split(" ")
        if len(tab) > 1:
            tab.pop(1)
            arry.append(tab)

    assert arry[0] == ["0", "0", "10", "4", "5"]
    assert arry[1] == ["1", "1", "11", "4", "5"]
    assert arry[2] == ["2", "2", "12", "4", "5"]
    assert arry[3] == ["3", "3", "13", "4", "5"]
    assert arry[4] == ["4", "4", "14", "4", "5"]
    assert arry[5] == ["5", "5", "15", "4", "5"]
    assert arry[6] == ["6", "6", "16", "4", "5"]
    assert arry[7] == ["7", "7", "17", "4", "5"]
    assert arry[8] == ["8", "8", "18", "4", "5"]
    assert arry[9] == ["9", "9", "19", "4", "5"]

    listener.kill()
