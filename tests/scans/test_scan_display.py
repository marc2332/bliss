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
from bliss.scanning.scan import ScanDisplay

import subprocess
import gevent
import pytest

# from bliss.shell.cli import repl
# repl.ERROR_REPORT.expert_mode = True


def grab_lines(
    subproc, lines, timeout=30, finish_line="PRESS F5 TO COME BACK TO THE SHELL PROMPT"
):
    try:
        with gevent.Timeout(timeout):
            for line in subproc.stdout:
                lines.append(line)
                # BREAK WHEN RECEIVING THE LAST SCAN DISPLAY LINE
                if finish_line in line:
                    break
    except gevent.Timeout:
        pass


def test_a2scan_display(session):
    """ PERFORM TESTS TO CHECK THE OUTPUT DISPLAYED BY THE ScanDataListener FOR THE DIFFERENT STANDARD SCANS"""

    sd = ScanDisplay(session.name)

    # put scan file in a different tmp directory or use SAVE = False
    # env_dict, session_obj = session
    # env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    # USE A PIPE TO PREVENT POPEN TO USE MAIN PROCESS TERMINAL STDIN (see blocking user input => bliss.data.display => termios.tcgetattr(fd))
    rp, wp = os.pipe()

    with subprocess.Popen(
        [sys.executable, "-u", "-m", "bliss.data.start_listener", "test_session"],
        stdin=rp,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as p:

        try:
            roby = session.config.get("roby")
            robz = session.config.get("robz")
            diode4 = session.config.get("diode4")
            diode5 = session.config.get("diode5")

            # WAIT FOR THE FIRST LINE (====== Bliss session 'test_session': watching scans ======)
            with gevent.Timeout(5):
                startline = p.stdout.readline()
                assert "Bliss session" in startline  # NOW LISTENER IS STARTED AND READY

            # ============= START THE A2SCAN ===================================
            lines = []
            # print('Start a2scan(robz, 0, 9, roby, 10, 19, 10, 0.01, diode4, diode5) ...', end='', flush=True)
            s = scans.a2scan(
                robz, 0, 9, roby, 10, 19, 10, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
                # line 2
                # line 3 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4 a2scan robz 0 9 roby 10 19 10 0.01
                # line 5
                # line 6             #         dt[s]      robz[mm]          roby        diode4        diode5
                # line 7             0             0             0            10             4             5
                # line 8             1      0.167275             1            11             4             5
                # line 9             2      0.364229             2            12             4             5
                # line 10            3      0.562693             3            13             4             5
                # line 11            4      0.727321             4            14             4             5
                # line 12            5        0.8995             5            15             4             5
                # line 13            6        1.0627             6            16             4             5
                # line 14            7       1.22539             7            17             4             5
                # line 15            8       1.38847             8            18             4             5
                # line 16            9       1.55273             9            19             4             5
                # line 17
                # line 18  Took 0:00:02.126591 (estimation was for 0:00:02.271460)
                # line 19
                # line 20  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]      robz[mm]          roby      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        tab.pop(3)
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

                # print(' finished')

            # ============= START THE A2SCAN (reversed axis) ===================
            lines = []
            # print('Start a2scan(roby, 0, 9, robz, 10, 19, 10, 0.01, diode4, diode5) ...', end='', flush=True)
            s = scans.a2scan(
                roby, 0, 9, robz, 10, 19, 10, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
                # line 2
                # line 3 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4 a2scan robz 0 9 roby 10 19 10 0.01
                # line 5
                # line 6             #         dt[s]          roby      robz[mm]        diode4        diode5
                # line 7             0             0             0            10             4             5
                # line 8             1      0.167275             1            11             4             5
                # line 9             2      0.364229             2            12             4             5
                # line 10            3      0.562693             3            13             4             5
                # line 11            4      0.727321             4            14             4             5
                # line 12            5        0.8995             5            15             4             5
                # line 13            6        1.0627             6            16             4             5
                # line 14            7       1.22539             7            17             4             5
                # line 15            8       1.38847             8            18             4             5
                # line 16            9       1.55273             9            19             4             5
                # line 17
                # line 18  Took 0:00:02.126591 (estimation was for 0:00:02.271460)
                # line 19
                # line 20  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]          roby      robz[mm]      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        tab.pop(3)
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

                # print(' finished')

            # ============= START THE A2SCAN (filtered counters) ================
            sd.counters = (diode4,)  # show only diode4
            lines = []
            # print('Start a2scan(robz, 0, 9, roby, 10, 19, 10, 0.01, diode4, diode5) ...', end='', flush=True)
            s = scans.a2scan(
                robz, 0, 9, roby, 10, 19, 10, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
                # line 2
                # line 3 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4 a2scan robz 0 9 roby 10 19 10 0.01
                # line 5
                # line 6             #         dt[s]      robz[mm]          roby        diode4
                # line 7             0             0             0            10             4
                # line 8             1      0.167275             1            11             4
                # line 9             2      0.364229             2            12             4
                # line 10            3      0.562693             3            13             4
                # line 11            4      0.727321             4            14             4
                # line 12            5        0.8995             5            15             4
                # line 13            6        1.0627             6            16             4
                # line 14            7       1.22539             7            17             4
                # line 15            8       1.38847             8            18             4
                # line 16            9       1.55273             9            19             4
                # line 17
                # line 18  Took 0:00:02.126591 (estimation was for 0:00:02.271460)
                # line 19
                # line 20  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]      robz[mm]          roby        diode4"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        arry.append(tab)

                assert arry[0] == ["0", "0", "10", "4"]
                assert arry[1] == ["1", "1", "11", "4"]
                assert arry[2] == ["2", "2", "12", "4"]
                assert arry[3] == ["3", "3", "13", "4"]
                assert arry[4] == ["4", "4", "14", "4"]
                assert arry[5] == ["5", "5", "15", "4"]
                assert arry[6] == ["6", "6", "16", "4"]
                assert arry[7] == ["7", "7", "17", "4"]
                assert arry[8] == ["8", "8", "18", "4"]
                assert arry[9] == ["9", "9", "19", "4"]

                # print(' finished')

            # ============= START THE ASCAN ===================================
            sd.counters = ()  # reset filtering, i.e show all
            lines = []
            # print('Start ascan(roby, 0, 9, 10, 0.1, diode4, diode5) ...', end='', flush=True)
            s = scans.ascan(roby, 0, 9, 10, 0.1, diode4, diode5, save=False)
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1  Total 4 points, 0:00:01.336231 (motion: 0:00:00.936231, count: 0:00:00.400000)
                # line 2
                # line 3  Scan 1056 Mon Apr 29 17:48:02 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4  ascan roby 0 1 4 0.1
                # line 5
                # line 6          #         dt[s]          roby        diode4        diode5
                # line 7          0             0             0             4             5
                # line 8          1      0.128761             1             4             5
                # line 9          2      0.260837             2             4             5
                # line 10         3      0.397228             3             4             5
                # line 11         4      0.529536             4             4             5
                # line 12         5      0.677317             5             4             5
                # line 13         6      0.821016             6             4             5
                # line 14         7      0.952247             7             4             5
                # line 15         8       1.06537             8             4             5
                # line 16         9       1.19704             9             4             5
                # line 17 Took 0:00:01.098092 (estimation was for 0:00:01.336231)
                # line 18
                # line 19 ================================== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==================================

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]          roby      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        tab.pop(2)
                        arry.append(tab)

                assert arry[0] == ["0", "0", "4", "5"]
                assert arry[1] == ["1", "1", "4", "5"]
                assert arry[2] == ["2", "2", "4", "5"]
                assert arry[3] == ["3", "3", "4", "5"]
                assert arry[4] == ["4", "4", "4", "5"]
                assert arry[5] == ["5", "5", "4", "5"]
                assert arry[6] == ["6", "6", "4", "5"]
                assert arry[7] == ["7", "7", "4", "5"]
                assert arry[8] == ["8", "8", "4", "5"]
                assert arry[9] == ["9", "9", "4", "5"]

                # print(' finished')

            # ============= START THE CT SCAN ===================================
            lines = []
            # print('Start ct(0.1,diode4,diode5) ...', end='', flush=True)
            s = scans.ct(0.1, diode4, diode5, save=False)
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1  Mon Apr 29 17:56:47 2019
                # line 2
                # line 3   dt[s] =          0.0 (         0.0/s)
                # line 4  diode4 =          4.0 (        40.0/s)
                # line 5  diode5 =          5.0 (        50.0/s)
                # line 6
                # line 7  Took 0:00:00.223051 (estimation was for 0:00:00.100000)
                # line 8
                # line 9  ======= >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ========

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                arry = []
                for line in lines[3:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")[:3]
                    if len(tab) > 1:
                        tab.pop(1)
                        arry.append(tab)

                assert arry[0] == ["dt[s]", "0.0"]
                assert arry[2] == ["diode4", "4.0"]
                assert arry[3] == ["diode5", "5.0"]

                # print(' finished')

            # ============= START THE LOOPSCAN ===================================
            lines = []
            # print('Start loopscan(10,0.1,diode4,diode5) ...', end='', flush=True)
            s = scans.loopscan(10, 0.1, diode4, diode5, save=False)
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1  Total 4 points, 0:00:01.336231 (motion: 0:00:00.936231, count: 0:00:00.400000)
                # line 2
                # line 3  Scan 1056 Mon Apr 29 17:48:02 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4  ascan roby 0 1 4 0.1
                # line 5
                # line 6          #         dt[s]        diode4        diode5
                # line 7          0             0             4             5
                # line 8          1      0.128761             4             5
                # line 9          2      0.260837             4             5
                # line 10         3      0.397228             4             5
                # line 11         4      0.529536             4             5
                # line 12         5      0.677317             4             5
                # line 13         6      0.821016             4             5
                # line 14         7      0.952247             4             5
                # line 15         8       1.06537             4             5
                # line 16         9       1.19704             4             5
                # line 17 Took 0:00:01.098092 (estimation was for 0:00:01.336231)
                # line 18
                # line 19 ================================== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==================================

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        tab.pop(1)
                        arry.append(tab)

                assert arry[0] == ["0", "4", "5"]
                assert arry[1] == ["1", "4", "5"]
                assert arry[2] == ["2", "4", "5"]
                assert arry[3] == ["3", "4", "5"]
                assert arry[4] == ["4", "4", "5"]
                assert arry[5] == ["5", "4", "5"]
                assert arry[6] == ["6", "4", "5"]
                assert arry[7] == ["7", "4", "5"]
                assert arry[8] == ["8", "4", "5"]
                assert arry[9] == ["9", "4", "5"]

                # print(' finished')

            # ============= START THE AMESH ======================================
            lines = []
            # print('Start amesh(roby,0,2,3,robz,10,12,3,0.01,diode4,diode5) ...', end='', flush=True)
            s = scans.amesh(
                roby, 0, 2, 3, robz, 10, 12, 3, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
                # line 2
                # line 3 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4 a2scan robz 0 9 roby 10 19 10 0.01
                # line 5
                # line 6             #         dt[s]          roby      robz[mm]        diode4        diode5
                # line 7             0             0             0            10             4             5
                # line 8             1      0.143428             1            10             4             5
                # line 9             2      0.287758             2            10             4             5
                # line 10            3      0.629851             0            11             4             5
                # line 11            4       0.77193             1            11             4             5
                # line 12            5      0.913047             2            11             4             5
                # line 13            6       1.26601             0            12             4             5
                # line 14            7       1.40803             1            12             4             5
                # line 15            8        1.5547             2            12             4             5
                # line 16
                # line 17  Took 0:00:02.126591 (estimation was for 0:00:02.271460)
                # line 18
                # line 19  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]          roby      robz[mm]      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        tab.pop(3)
                        arry.append(tab)

                assert arry[0] == ["0", "0", "10", "4", "5"]
                assert arry[1] == ["1", "1", "10", "4", "5"]
                assert arry[2] == ["2", "2", "10", "4", "5"]
                assert arry[3] == ["3", "0", "11", "4", "5"]
                assert arry[4] == ["4", "1", "11", "4", "5"]
                assert arry[5] == ["5", "2", "11", "4", "5"]
                assert arry[6] == ["6", "0", "12", "4", "5"]
                assert arry[7] == ["7", "1", "12", "4", "5"]
                assert arry[8] == ["8", "2", "12", "4", "5"]

                # print(' finished')

            # ============= START THE LOOKUPSCAN ==================================
            lines = []
            # print('Start lookupscan(0.01,roby,(0.5,1.2,2.2,33.3),diode4,diode5) ...', end='', flush=True)
            s = scans.lookupscan(
                0.01, roby, (0.5, 1.2, 2.2, 33.3), diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
                # line 2
                # line 3 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4 a2scan robz 0 9 roby 10 19 10 0.01
                # line 5
                # line 6             #         dt[s]          roby        diode4        diode5
                # line 7             0             0           0.5             4             5
                # line 8             1      0.143428           1.2             4             5
                # line 9             2      0.287758           2.2             4             5
                # line 10            3      0.629851          33.3             4             5
                # line 11
                # line 12  Took 0:00:02.126591 (estimation was for 0:00:02.271460)
                # line 13
                # line 14  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]          roby      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 2:
                        tab.pop(1)
                        tab.pop(2)
                        arry.append(tab)

                assert arry[0] == ["0", "0.5", "4", "5"]
                assert arry[1] == ["1", "1.2", "4", "5"]
                assert arry[2] == ["2", "2.2", "4", "5"]
                assert arry[3] == ["3", "33.3", "4", "5"]

                # print(' finished')

            # ============= START THE POINTSCAN ==================================
            lines = []
            # print('Start pointscan(roby,(0.5,1.1,2.2),0.1,diode4,diode5) ...', end='', flush=True)
            s = scans.pointscan(roby, (0.5, 1.1, 2.2), 0.1, diode4, diode5, save=False)
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1 Total 10 points, 0:00:02.271460 (motion: 0:00:02.171460, count: 0:00:00.100000)
                # line 2
                # line 3 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 4 a2scan robz 0 9 roby 10 19 10 0.01
                # line 5
                # line 6             #         dt[s]          roby        diode4        diode5
                # line 7             0             0           0.5             4             5
                # line 8             1      0.143428           1.1             4             5
                # line 9             2      0.287758           2.2             4             5
                # line 10
                # line 11  Took 0:00:02.126591 (estimation was for 0:00:02.271460)
                # line 12
                # line 13  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[6].strip()
                    == "#         dt[s]          roby      epoch[s]        diode4        diode5"
                )

                arry = []
                for line in lines[7:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 2:
                        tab.pop(1)
                        tab.pop(2)
                        arry.append(tab)

                assert arry[0] == ["0", "0.5", "4", "5"]
                assert arry[1] == ["1", "1.1", "4", "5"]
                assert arry[2] == ["2", "2.2", "4", "5"]

                # print(' finished')

        finally:

            p.terminate()
