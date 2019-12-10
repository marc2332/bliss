# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import sys
import numpy

from bliss.data import start_listener
from bliss.common import scans
from bliss.scanning.scan import ScanDisplay

from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.chain import AcquisitionChain, AcquisitionSlave
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.acquisition import timer

import subprocess
import gevent
import pytest


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
        raise TimeoutError


def test_fast_scan_display(session):
    class BlockDataDevice(AcquisitionSlave):
        def __init__(self, npoints, chunk):
            super().__init__(
                None,
                name="block_data_device",
                npoints=npoints,
                prepare_once=True,
                start_once=True,
            )
            self.event = gevent.event.Event()
            self.channels.append(AcquisitionChannel("block_data", numpy.int, ()))
            self.pending_trigger = 0
            self.chunk = chunk

        def prepare(self):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def trigger(self):
            self.pending_trigger += 1
            self.event.set()

        def wait_ready(self):
            return True

        def reading(self):
            data = numpy.arange(self.npoints, dtype=numpy.int)
            acq_npoint = 0
            chunk = self.chunk
            i = 0
            while acq_npoint < self.npoints:

                while not self.pending_trigger:
                    self.event.clear()
                    self.event.wait()

                self.pending_trigger -= 1

                if (acq_npoint + 1) % (chunk) == 0 and acq_npoint:
                    self.channels[0].emit(data[i * chunk : (i + 1) * chunk])
                    i += 1

                acq_npoint += 1

            if self.npoints - i * chunk > 0:
                self.channels[0].emit(data[i * chunk :])

    nb = 1234
    chunk = 20

    soft_timer = timer.SoftwareTimerMaster(0, npoints=nb)
    block_data_device = BlockDataDevice(nb, chunk)
    acq_chain = AcquisitionChain()
    acq_chain.add(soft_timer, block_data_device)

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

            # WAIT FOR THE FIRST LINE (====== Bliss session 'test_session': watching scans ======)
            with gevent.Timeout(5):
                startline = p.stdout.readline()
                assert "Bliss session" in startline  # NOW LISTENER IS STARTED AND READY

            # ============= START THE SCAN ===================================
            lines = []

            s = Scan(
                acq_chain,
                scan_info={"type": "fast_scan", "npoints": nb},
                save=False,
                save_images=False,
                data_watch_callback=StepScanDataWatch(),
            )
            s.run()

            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2 Scan 1268 Wed May 15 17:58:41 2019 <no saving> test_session user = pguillou
                # line 3 scan
                # line 4
                # line 5               #         dt[s]    block_data
                # line 6               0             0             0
                # line 7               1      0.167275             1
                # line 8               2      0.364229             2
                # line 9               3      0.562693             3
                # line 10              4      0.727321             4
                # line 11              5        0.8995             5
                # line 12              6        1.0627             6
                # line 13              7       1.22539             7
                # line 14              8       1.38847             8
                # line 15              9       1.55273             9
                # ..................................................
                # line 1240         1233       xxxxxxx          1233
                # line 1241
                # line 1242  Took 0:00:02.126591
                # line 1243
                # line 1244  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert lines[5].strip() == "#         dt[s]    block_data"

                arry = []
                for line in lines[6:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
                        arry.append(tab)

                for i in range(nb):
                    assert arry[i] == [str(i), str(i)]

        finally:
            p.terminate()


def test_standard_scan_display(session):
    """ PERFORM TESTS TO CHECK THE OUTPUT DISPLAYED BY THE ScanDataListener FOR THE DIFFERENT STANDARD SCANS"""

    sd = ScanDisplay(session.name)

    # put scan file in a different tmp directory or use SAVE = False
    # env_dict, session_obj = session
    # session.scan_saving.base_path = str(scan_tmpdir)

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
            # print('Start a2scan(robz, 0, 9, roby, 10, 19, 9, 0.01, diode4, diode5) ...', end='', flush=True)
            s = scans.a2scan(
                robz, 0, 9, roby, 10, 19, 9, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3 a2scan robz 0 9 roby 10 19 10 0.01
                # line 4
                # line 5             #         dt[s]      robz[mm]          roby        diode4        diode5
                # line 6             0             0             0            10             4             5
                # line 7             1      0.167275             1            11             4             5
                # line 8             2      0.364229             2            12             4             5
                # line 9             3      0.562693             3            13             4             5
                # line 10            4      0.727321             4            14             4             5
                # line 11            5        0.8995             5            15             4             5
                # line 12            6        1.0627             6            16             4             5
                # line 13            7       1.22539             7            17             4             5
                # line 14            8       1.38847             8            18             4             5
                # line 15            9       1.55273             9            19             4             5
                # line 16
                # line 17  Took 0:00:02.126591
                # line 18
                # line 19  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]      robz[mm]          roby        diode4        diode5"
                )

                arry = []
                for line in lines[6:]:
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

                # print(' finished')

            # ============= START THE A2SCAN (reversed axis) ===================
            lines = []
            # print('Start a2scan(roby, 0, 9, robz, 10, 19, 9, 0.01, diode4, diode5) ...', end='', flush=True)
            s = scans.a2scan(
                roby, 0, 9, robz, 10, 19, 9, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3 a2scan robz 0 9 roby 10 19 10 0.01
                # line 4
                # line 5             #         dt[s]          roby      robz[mm]        diode4        diode5
                # line 6             0             0             0            10             4             5
                # line 7             1      0.167275             1            11             4             5
                # line 8             2      0.364229             2            12             4             5
                # line 9            3      0.562693             3            13             4             5
                # line 10            4      0.727321             4            14             4             5
                # line 11            5        0.8995             5            15             4             5
                # line 12            6        1.0627             6            16             4             5
                # line 13            7       1.22539             7            17             4             5
                # line 14            8       1.38847             8            18             4             5
                # line 15            9       1.55273             9            19             4             5
                # line 16
                # line 17  Took 0:00:02.126591
                # line 18
                # line 19  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]          roby      robz[mm]        diode4        diode5"
                )

                arry = []
                for line in lines[6:]:
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

                # print(' finished')

            # ============= START THE A2SCAN (filtered counters) ================
            sd.counters = (diode4,)  # show only diode4
            lines = []
            # print('Start a2scan(robz, 0, 9, roby, 10, 19, 9, 0.01, diode4, diode5) ...', end='', flush=True)
            s = scans.a2scan(
                robz, 0, 9, roby, 10, 19, 9, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3 a2scan robz 0 9 roby 10 19 10 0.01
                # line 4
                # line 5             #         dt[s]      robz[mm]          roby        diode4
                # line 6             0             0             0            10             4
                # line 7             1      0.167275             1            11             4
                # line 8             2      0.364229             2            12             4
                # line 9             3      0.562693             3            13             4
                # line 10            4      0.727321             4            14             4
                # line 11            5        0.8995             5            15             4
                # line 12            6        1.0627             6            16             4
                # line 13            7       1.22539             7            17             4
                # line 14            8       1.38847             8            18             4
                # line 15            9       1.55273             9            19             4
                # line 16
                # line 17  Took 0:00:02.126591
                # line 18
                # line 19  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]      robz[mm]          roby        diode4"
                )

                arry = []
                for line in lines[6:]:
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
            # print('Start ascan(roby, 0, 9, 9, 0.1, diode4, diode5) ...', end='', flush=True)
            s = scans.ascan(roby, 0, 9, 9, 0.1, diode4, diode5, save=False)
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2  Scan 1056 Mon Apr 29 17:48:02 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3  ascan roby 0 1 4 0.1
                # line 4
                # line 5          #         dt[s]          roby        diode4        diode5
                # line 6          0             0             0             4             5
                # line 7          1      0.128761             1             4             5
                # line 8          2      0.260837             2             4             5
                # line 9          3      0.397228             3             4             5
                # line 10         4      0.529536             4             4             5
                # line 11         5      0.677317             5             4             5
                # line 12         6      0.821016             6             4             5
                # line 13         7      0.952247             7             4             5
                # line 14         8       1.06537             8             4             5
                # line 15         9       1.19704             9             4             5
                # line 16 Took 0:00:01.098092
                # line 17
                # line 18 ================================== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==================================

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]          roby        diode4        diode5"
                )

                arry = []
                for line in lines[6:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
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
                # line 7  Took 0:00:00.223051
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
                assert arry[1] == ["diode4", "4.0"]
                assert arry[2] == ["diode5", "5.0"]

                # print(' finished')

            # ============= START THE LOOPSCAN ===================================
            lines = []
            # print('Start loopscan(10,0.1,diode4,diode5) ...', end='', flush=True)
            s = scans.loopscan(10, 0.1, diode4, diode5, save=False)
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2  Scan 1056 Mon Apr 29 17:48:02 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3  ascan roby 0 1 4 0.1
                # line 4
                # line 5          #         dt[s]        diode4        diode5
                # line 6          0             0             4             5
                # line 7          1      0.128761             4             5
                # line 8          2      0.260837             4             5
                # line 9          3      0.397228             4             5
                # line 10         4      0.529536             4             5
                # line 11         5      0.677317             4             5
                # line 12         6      0.821016             4             5
                # line 13         7      0.952247             4             5
                # line 14         8       1.06537             4             5
                # line 15         9       1.19704             4             5
                # line 16 Took 0:00:01.098092
                # line 17
                # line 18 ================================== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==================================

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert lines[5].strip() == "#         dt[s]        diode4        diode5"

                arry = []
                for line in lines[6:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
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
            # print('Start amesh(roby,0,2,2,robz,10,12,2,0.01,diode4,diode5) ...', end='', flush=True)
            s = scans.amesh(
                roby, 0, 2, 2, robz, 10, 12, 2, 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3 a2scan robz 0 9 roby 10 19 10 0.01
                # line 4
                # line 5             #         dt[s]          roby      robz[mm]        diode4        diode5
                # line 6             0             0             0            10             4             5
                # line 7             1      0.143428             1            10             4             5
                # line 8             2      0.287758             2            10             4             5
                # line 9             3      0.629851             0            11             4             5
                # line 10            4       0.77193             1            11             4             5
                # line 11            5      0.913047             2            11             4             5
                # line 12            6       1.26601             0            12             4             5
                # line 13            7       1.40803             1            12             4             5
                # line 14            8        1.5547             2            12             4             5
                # line 15
                # line 16  Took 0:00:02.126591
                # line 17
                # line 18  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]          roby      robz[mm]        diode4        diode5"
                )

                arry = []
                for line in lines[6:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 1:
                        tab.pop(1)
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
                [(roby, (0.5, 1.2, 2.2, 33.3))], 0.01, diode4, diode5, save=False
            )
            # EXPECTED OUTPUT
            if 1:
                # line 0
                # line 1
                # line 2 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3 a2scan robz 0 9 roby 10 19 10 0.01
                # line 4
                # line 5             #         dt[s]          roby        diode4        diode5
                # line 6             0             0           0.5             4             5
                # line 7             1      0.143428           1.2             4             5
                # line 8             2      0.287758           2.2             4             5
                # line 9            3      0.629851          33.3             4             5
                # line 10
                # line 11  Took 0:00:02.126591
                # line 12
                # line 13  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]          roby        diode4        diode5"
                )

                arry = []
                for line in lines[6:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 2:
                        tab.pop(1)
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
                # line 1
                # line 2 Scan 937 Fri Apr 26 16:57:07 2019 /tmp/scans/test_session/data.h5 test_session user = pguillou
                # line 3 a2scan robz 0 9 roby 10 19 10 0.01
                # line 4
                # line 5             #         dt[s]          roby        diode4        diode5
                # line 6             0             0           0.5             4             5
                # line 7             1      0.143428           1.1             4             5
                # line 8             2      0.287758           2.2             4             5
                # line 9
                # line 10  Took 0:00:02.126591
                # line 11
                # line 12  ============== >>> PRESS F5 TO COME BACK TO THE SHELL PROMPT <<< ==============

                # GRAB THE SCAN DISPLAY LINES
                grab_lines(p, lines)

                assert (
                    lines[5].strip()
                    == "#         dt[s]          roby        diode4        diode5"
                )

                arry = []
                for line in lines[6:]:
                    line = " ".join(line.strip().split())
                    tab = line.split(" ")
                    if len(tab) > 2:
                        tab.pop(1)
                        arry.append(tab)

                assert arry[0] == ["0", "0.5", "4", "5"]
                assert arry[1] == ["1", "1.1", "4", "5"]
                assert arry[2] == ["2", "2.2", "4", "5"]

                # print(' finished')

        finally:

            p.terminate()


def test_lima_sim_bpm_display_names(beacon, default_session, lima_simulator):
    simulator = beacon.get("lima_simulator")
    diode = beacon.get("diode")

    s = scans.loopscan(
        1, 0.1, simulator.counter_groups.bpm, diode, save=False, run=False
    )

    display_names_values = s.scan_info["acquisition_chain"]["timer"][
        "display_names"
    ].values()
    for cnt_name in ("x", "y", "fwhm_x", "fwhm_y", "acq_time", "intensity"):
        # only 1 BPM from 1 camera => display names are short names
        assert f"{cnt_name}" in display_names_values
    assert "diode" in display_names_values


def test_lima_sim_2_bpms_display_names(
    beacon, default_session, lima_simulator, lima_simulator2
):
    simulator = beacon.get("lima_simulator")
    simulator2 = beacon.get("lima_simulator2")

    s = scans.loopscan(
        1,
        0.1,
        simulator.counter_groups.bpm,
        simulator2.counter_groups.bpm,
        save=False,
        run=False,
    )

    display_names_values = s.scan_info["acquisition_chain"]["timer"][
        "display_names"
    ].values()
    for cnt_name in ("x", "y", "fwhm_x", "fwhm_y", "acq_time", "intensity"):
        assert f"{simulator.name}:bpm:{cnt_name}" in display_names_values
        assert f"{simulator2.name}:bpm:{cnt_name}" in display_names_values


def test_lima_bpm_alias(beacon, default_session, lima_simulator):
    simulator = beacon.get("lima_simulator")

    ALIASES = default_session.env_dict["ALIASES"]
    ALIASES.add("toto", simulator.bpm.x)

    s = scans.loopscan(1, 0.1, simulator.bpm.x, save=False, run=False)

    display_names_values = s.scan_info["acquisition_chain"]["timer"][
        "display_names"
    ].values()
    assert "toto" in display_names_values
