# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import sys
import subprocess
import gevent
import numpy
import pytest
from contextlib import contextmanager
from bliss.common import scans
from bliss.common.measurementgroup import MeasurementGroup
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.chain import AcquisitionChain, AcquisitionSlave
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.acquisition import timer
from bliss.scanning.scan_display import ScanDisplay


@contextmanager
def grab_lines(subproc, timeout=30, finish_line="Took "):
    lines = []
    try:
        with gevent.Timeout(timeout):
            for line in subproc.stdout:
                lines.append(line)
                if finish_line in line:
                    break
    except gevent.Timeout:
        print("".join(lines))
        raise TimeoutError

    try:
        yield lines
    except Exception:
        print("".join(lines))
        raise


def find_data_start(lines, fields):
    """Check the content of the expected header and return the location of the
    data.

    Raises an exception if the header was not found or if the header was not
    containing expected value.
    """
    col_sep = "|"
    offset = 2
    for idx, line in enumerate(lines):
        ans = [l.strip() for l in line.split(col_sep)]
        if len(ans) >= 0 and ans[0] == "#":
            if len(ans) != len(fields) or False in [
                ans[i] == fields[i] for i in range(len(fields))
            ]:
                raise Exception("Unexpected content %s (found %s)" % (fields, ans))
            return idx + offset

    raise Exception("Data header not found")


def extract_data(lines, shape, col_sep="|"):
    """ extract text data as numpy array """
    _h, w = shape
    arry = numpy.empty(shape, dtype=numpy.float)

    incr = 0
    for line in lines:
        ans = line.strip().split(col_sep)
        if len(ans) == w:
            arry[incr][:] = [float(v) for v in ans]
            incr += 1

    return arry


def extract_words(lines, col_sep="|", cast_num=True):
    """ extract text data as a list of strings """
    nlines = []
    for line in lines:
        ans = line.strip().split(col_sep)

        if cast_num:
            words = []
            for w in ans:
                try:
                    w = float(w)
                except Exception:
                    w = w.strip()
                words.append(w)
        else:
            words = [w.strip() for w in ans]

        nlines.append(words)

    return nlines


def wait_for_scan_data_listener_started(popipe):
    # WAIT FOR THE FIRST LINE (>>>>> Watching scans from Bliss session: 'test_session' <<<<)
    with gevent.Timeout(5):
        startline = "\n"
        while startline == "\n":
            startline = popipe.stdout.readline()

        assert (
            "Watching scans from Bliss session" in startline
        )  # NOW LISTENER IS STARTED AND READY


@contextmanager
def disable_scan_display_filter():
    try:
        scan_display = ScanDisplay()
        old = scan_display.scan_display_filter_enabled
        scan_display.scan_display_filter_enabled = False
        yield
    finally:
        scan_display.scan_display_filter_enabled = old


@pytest.fixture()
def scan_data_listener_process(session):
    """Fixture to check the output displayed by the ScanDataListener for
    the different standard scans"""
    # USE A PIPE TO PREVENT POPEN TO USE MAIN PROCESS TERMINAL STDIN (see blocking user input => bliss.shell.data.display => termios.tcgetattr(fd))
    rp, _wp = os.pipe()

    with disable_scan_display_filter():
        with subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "bliss.shell.data.start_listener",
                "test_session",
            ],
            stdin=rp,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as p:
            try:
                wait_for_scan_data_listener_started(p)
                yield p
            finally:
                p.terminate()


def test_fast_scan_display(session, scan_data_listener_process):
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

    s = Scan(
        acq_chain,
        scan_info={"type": "fast_scan", "npoints": nb},
        save=False,
        save_images=False,
        data_watch_callback=StepScanDataWatch(),
    )
    s.run()

    # EXPECTED OUTPUT
    #                |   timer    |
    #                |     -      |
    #         #      |   dt[s]    | block_data
    #    ------------|------------|------------
    #         0      |  0.00000   |  0.00000
    #         1      |0.000756025 |  1.00000
    #         2      | 0.00124764 |  2.00000
    #         3      | 0.00176120 |  3.00000
    #         4      | 0.00224543 |  4.00000
    #         5      | 0.00273418 |  5.00000
    #         6      | 0.00320554 |  6.00000
    #         7      | 0.00368118 |  7.00000
    #         8      | 0.00415182 |  8.00000
    #         9      | 0.00499439 |  9.00000
    #         10     | 0.00548410 |  10.0000
    #         11     | 0.00596142 |  11.0000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "block_data"]
        data_start_idx = find_data_start(lines, labels)

        arry = extract_data(lines[data_start_idx:], (nb, 3))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nb):
            assert numpy.all(arry[i, :] == [i, i])


def test_scan_display_a2scan(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with a2scan"""
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    scans.a2scan(robz, 0, 9, roby, 10, 19, 9, 0.01, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |    axis    |    axis    |..controller|..controller
    #                |     -      |     -      |     -      |     -      |     -
    #         #      |   dt[s]    |  robz[mm]  |    roby    |   diode4   |   diode5
    #    ------------|------------|------------|------------|------------|------------
    #         0      |  0.00000   |  0.00000   |  10.0000   |  4.00000   |  5.00000
    #         1      |  0.252048  |  1.00000   |  11.0000   |  4.00000   |  5.00000
    #         2      |  0.478536  |  2.00000   |  12.0000   |  4.00000   |  5.00000
    #         3      |  0.717785  |  3.00000   |  13.0000   |  4.00000   |  5.00000
    #         4      |  0.972510  |  4.00000   |  14.0000   |  4.00000   |  5.00000
    #         5      |  1.22692   |  5.00000   |  15.0000   |  4.00000   |  5.00000
    #         6      |  1.47112   |  6.00000   |  16.0000   |  4.00000   |  5.00000
    #         7      |  1.71941   |  7.00000   |  17.0000   |  4.00000   |  5.00000
    #         8      |  1.97158   |  8.00000   |  18.0000   |  4.00000   |  5.00000
    #         9      |  2.23130   |  9.00000   |  19.0000   |  4.00000   |  5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "robz[mm]", "roby", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 10
        arry = extract_data(lines[data_start_idx:], (nbp, 6))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, i, i + 10, 4, 5])


def test_scan_display_a2scan_reverse(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with a2scan (reversed axis)"""
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    scans.a2scan(roby, 0, 9, robz, 10, 19, 9, 0.01, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |    axis    |    axis    |..controller|..controller
    #                |     -      |     -      |     -      |     -      |     -
    #         #      |   dt[s]    |    roby    |  robz[mm]  |   diode4   |   diode5
    #    ------------|------------|------------|------------|------------|------------
    #         0      |  0.00000   |  0.00000   |  10.0000   |  4.00000   |  5.00000
    #         1      |  0.252455  |  1.00000   |  11.0000   |  4.00000   |  5.00000
    #         2      |  0.501949  |  2.00000   |  12.0000   |  4.00000   |  5.00000
    #         3      |  0.764905  |  3.00000   |  13.0000   |  4.00000   |  5.00000
    #         4      |  1.02001   |  4.00000   |  14.0000   |  4.00000   |  5.00000
    #         5      |  1.28091   |  5.00000   |  15.0000   |  4.00000   |  5.00000
    #         6      |  1.54364   |  6.00000   |  16.0000   |  4.00000   |  5.00000
    #         7      |  1.78826   |  7.00000   |  17.0000   |  4.00000   |  5.00000
    #         8      |  2.01668   |  8.00000   |  18.0000   |  4.00000   |  5.00000
    #         9      |  2.26631   |  9.00000   |  19.0000   |  4.00000   |  5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "roby", "robz[mm]", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 10
        arry = extract_data(lines[data_start_idx:], (nbp, 6))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, i, i + 10, 4, 5])


def test_scan_display_ascan(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with ascan"""
    roby = session.config.get("roby")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    scans.ascan(roby, 0, 9, 9, 0.1, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |    axis    |..pling_controller|..pling_controller
    #                |     -      |     -      |        -         |        -
    #         #      |   dt[s]    |    roby    |      diode4      |      diode5
    #    ------------|------------|------------|------------------|------------------
    #         0      |  0.00000   |  0.00000   |     4.00000      |     5.00000
    #         1      |  0.258994  |  1.00000   |     4.00000      |     5.00000
    #         2      |  0.519995  |  2.00000   |     4.00000      |     5.00000
    #         3      |  0.783957  |  3.00000   |     4.00000      |     5.00000
    #         4      |  1.04765   |  4.00000   |     4.00000      |     5.00000
    #         5      |  1.30581   |  5.00000   |     4.00000      |     5.00000
    #         6      |  1.56437   |  6.00000   |     4.00000      |     5.00000
    #         7      |  1.81697   |  7.00000   |     4.00000      |     5.00000
    #         8      |  2.07680   |  8.00000   |     4.00000      |     5.00000
    #         9      |  2.33725   |  9.00000   |     4.00000      |     5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "roby", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 10
        arry = extract_data(lines[data_start_idx:], (nbp, 5))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, i, 4, 5])


def test_scan_display_ct(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with ct scan"""
    diode0 = session.config.get("diode0")
    diode1 = session.config.get("diode1")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    scans.ct(0.1, diode0, diode1, diode4, diode5)

    # EXPECTED OUTPUT
    # diode0  =      -2.00000     (    -20.0000        /s)  simulation_diode_sampling_controller
    # diode1  =       3.00000e+07 (      3.00000e+08   /s)  simulation_diode_sampling_controller
    # diode4  =       4.00000     (     40.0000        /s)  simulation_diode_sampling_controller
    # diode5  =       5.00000     (     50.0000        /s)  simulation_diode_sampling_controller

    with grab_lines(scan_data_listener_process) as lines:
        line_diode0 = "diode0  =  -123456.          (      -1.23456e+06   /s)  simulation_diode_sampling_controller"
        line_diode1 = "diode1  =        3.00000e+07 (       3.00000e+08   /s)  simulation_diode_sampling_controller"
        line_diode4 = "diode4  =        4.00000     (      40.0000        /s)  simulation_diode_sampling_controller"
        line_diode5 = "diode5  =        5.00000     (      50.0000        /s)  simulation_diode_sampling_controller"
        assert lines[10].strip() == line_diode0
        assert lines[11].strip() == line_diode1
        assert lines[12].strip() == line_diode4
        assert lines[13].strip() == line_diode5


def test_scan_display_loopscan(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with ascan"""
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    scans.loopscan(10, 0.1, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |..de_sampling_controller|..de_sampling_controller
    #                |     -      |           -            |           -
    #         #      |   dt[s]    |         diode4         |         diode5
    #    ------------|------------|------------------------|------------------------
    #         0      |  0.00000   |        4.00000         |        5.00000
    #         1      |  0.102292  |        4.00000         |        5.00000
    #         2      |  0.203329  |        4.00000         |        5.00000
    #         3      |  0.305624  |        4.00000         |        5.00000
    #         4      |  0.407249  |        4.00000         |        5.00000
    #         5      |  0.508064  |        4.00000         |        5.00000
    #         6      |  0.609728  |        4.00000         |        5.00000
    #         7      |  0.711477  |        4.00000         |        5.00000
    #         8      |  0.812464  |        4.00000         |        5.00000
    #         9      |  0.914200  |        4.00000         |        5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 10
        arry = extract_data(lines[data_start_idx:], (nbp, 4))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, 4, 5])


def test_scan_display_amesh(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with ascan"""
    roby = session.config.get("roby")
    robz = session.config.get("robz")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    scans.amesh(roby, 0, 2, 2, robz, 10, 12, 2, 0.01, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |    axis    |    axis    |..controller|..controller
    #                |     -      |     -      |     -      |     -      |     -
    #         #      |   dt[s]    |    roby    |  robz[mm]  |   diode4   |   diode5
    #    ------------|------------|------------|------------|------------|------------
    #         0      |  0.00000   |  0.00000   |  10.0000   |  4.00000   |  5.00000
    #         1      |  0.175061  |  1.00000   |  10.0000   |  4.00000   |  5.00000
    #         2      |  0.377336  |  2.00000   |  10.0000   |  4.00000   |  5.00000
    #         3      |  0.801528  |  0.00000   |  11.0000   |  4.00000   |  5.00000
    #         4      |  0.975771  |  1.00000   |  11.0000   |  4.00000   |  5.00000
    #         5      |  1.15545   |  2.00000   |  11.0000   |  4.00000   |  5.00000
    #         6      |  1.53510   |  0.00000   |  12.0000   |  4.00000   |  5.00000
    #         7      |  1.67935   |  1.00000   |  12.0000   |  4.00000   |  5.00000
    #         8      |  1.83801   |  2.00000   |  12.0000   |  4.00000   |  5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "roby", "robz[mm]", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 9
        arry = extract_data(lines[data_start_idx:], (nbp, 6))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, i % 3, 10 + i // 3, 4, 5])


def test_scan_display_lookupscan(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with ascan"""
    roby = session.config.get("roby")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    pos = (0.5, 1.2, 2.2, 33.3)
    scans.lookupscan([(roby, pos)], 0.01, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |    axis    |..pling_controller|..pling_controller
    #                |     -      |     -      |        -         |        -
    #         #      |   dt[s]    |    roby    |      diode4      |      diode5
    #    ------------|------------|------------|------------------|------------------
    #         0      |  0.00000   |  0.500000  |     4.00000      |     5.00000
    #         1      |  0.114702  |  1.20000   |     4.00000      |     5.00000
    #         2      |  0.277584  |  2.20000   |     4.00000      |     5.00000
    #         3      |  0.719908  |  33.3000   |     4.00000      |     5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "roby", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 4
        arry = extract_data(lines[data_start_idx:], (nbp, 5))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, pos[i], 4, 5])


def test_scan_display_pointscan(session, scan_data_listener_process):
    """Check the output displayed by the ScanDataListener with ascan"""
    roby = session.config.get("roby")
    diode4 = session.config.get("diode4")
    diode5 = session.config.get("diode5")
    pos = (0.5, 1.1, 2.2)
    scans.pointscan(roby, pos, 0.1, diode4, diode5, save=False)

    # EXPECTED OUTPUT
    #                |   timer    |    axis    |..pling_controller|..pling_controller
    #                |     -      |     -      |        -         |        -
    #         #      |   dt[s]    |    roby    |      diode4      |      diode5
    #    ------------|------------|------------|------------------|------------------
    #         0      |  0.00000   |  0.500000  |     4.00000      |     5.00000
    #         1      |  0.207738  |  1.10000   |     4.00000      |     5.00000
    #         2      |  0.452876  |  2.20000   |     4.00000      |     5.00000

    with grab_lines(scan_data_listener_process) as lines:
        labels = ["#", "dt[s]", "roby", "diode4", "diode5"]
        data_start_idx = find_data_start(lines, labels)

        nbp = 3
        arry = extract_data(lines[data_start_idx:], (nbp, 5))
        arry = numpy.delete(arry, 1, 1)  # remove column dt
        for i in range(nbp):
            assert numpy.all(arry[i, :] == [i, pos[i], 4, 5])


def test_lima_sim_bpm_display_names(beacon, default_session, lima_simulator):
    simulator = beacon.get("lima_simulator")
    diode = beacon.get("diode")

    s = scans.loopscan(
        1, 0.1, simulator.counter_groups.bpm, diode, save=False, run=False
    )

    display_names_values = [
        v["display_name"]
        for _, v in s.scan_info["channels"].items()
        if "display_name" in v
    ]
    for cnt_name in ("x", "y", "fwhm_x", "fwhm_y", "acq_time", "intensity", "diode"):
        # only 1 BPM from 1 camera => display names are short names
        assert f"{cnt_name}" in display_names_values


def test_lima_bpm_alias(beacon, default_session, lima_simulator):
    simulator = beacon.get("lima_simulator")

    ALIASES = default_session.env_dict["ALIASES"]
    ALIASES.add("toto", simulator.bpm.x)

    s = scans.loopscan(1, 0.1, simulator.bpm.x, save=False, run=False)

    display_names_values = [
        v["display_name"]
        for _, v in s.scan_info["channels"].items()
        if "display_name" in v
    ]
    assert "toto" in display_names_values


def test_counters_display_order(session, scan_data_listener_process):
    """Check the output displayed by a scan with counters from MG or from given counters/controllers are sorted the same"""

    from bliss.controllers.simulation_diode import (
        SimulationDiodeController,
        SimulationDiodeSamplingCounter,
    )

    ctrl = SimulationDiodeController()
    names = ["Can", "you", "read", "this", "message", "from", "alpha", "to", "omega"]
    cnts = [
        SimulationDiodeSamplingCounter(name, ctrl) for name in names
    ]  # all cnts share the same controller

    ctrl2 = SimulationDiodeController()
    names2 = ["The", "hawl", "is", "sleeping", "in", "the", "barn"]
    cnts2 = [
        SimulationDiodeSamplingCounter(name, ctrl2) for name in names2
    ]  # another counter controller

    cnt_num = len(names)
    cnt_num2 = len(names2)

    all_cnts = cnts + cnts2
    all_names = names + names2
    all_names_r = names2 + names
    all_cnt_num = cnt_num + cnt_num2

    # print('names =>', names)
    # print('ctrl.counters =>', [c.name for c in ctrl.counters])

    # Measurement group
    mg1 = MeasurementGroup("mygroup1", {"counters": [cnt.fullname for cnt in cnts]})
    mg1.set_active()

    assert [c.split(":")[-1] for c in mg1.enabled] == names

    # Check that order of counters from a list of counters is maintained
    scans.ct(0.01, *all_cnts)
    with grab_lines(scan_data_listener_process) as lines:
        # print("\n".join(lines))
        for idx, line in enumerate(lines[10 : 10 + all_cnt_num]):
            cname = line.split("=")[0].strip()
            assert cname == all_names[idx]

    # Check that order of counters from controller is maintained
    scans.ct(0.01, ctrl, ctrl2)
    with grab_lines(scan_data_listener_process) as lines:
        # print("\n".join(lines))
        for idx, line in enumerate(lines[10 : 10 + all_cnt_num]):
            cname = line.split("=")[0].strip()
            assert cname == all_names[idx]

    scans.ct(0.01, ctrl2, ctrl)
    with grab_lines(scan_data_listener_process) as lines:
        # print("\n".join(lines))
        for idx, line in enumerate(lines[10 : 10 + all_cnt_num]):
            cname = line.split("=")[0].strip()
            assert cname == all_names_r[idx]

    # Check that order of counters from MG is maintained
    scans.ct(0.01, mg1)
    with grab_lines(scan_data_listener_process) as lines:
        # print("\n".join(lines))
        for idx, line in enumerate(lines[10 : 10 + cnt_num]):
            cname = line.split("=")[0].strip()
            assert cname == names[idx]

    # Check that order of counters from default MG is maintained
    scans.ct(0.01)
    with grab_lines(scan_data_listener_process) as lines:
        # print("\n".join(lines))
        for idx, line in enumerate(lines[10 : 10 + cnt_num]):
            cname = line.split("=")[0].strip()
            assert cname == names[idx]

    # Check that order is maintained even if duplicating counters
    rnames = all_names[:]  # to check that all cnts were displayed

    scans.ct(0.01, mg1, ctrl, ctrl2, ctrl)
    with grab_lines(scan_data_listener_process) as lines:
        # print("\n".join(lines))
        for idx, line in enumerate(lines[10 : 10 + all_cnt_num]):
            cname = line.split("=")[0].strip()
            assert cname == all_names[idx]

            rnames.remove(cname)
    assert rnames == []
