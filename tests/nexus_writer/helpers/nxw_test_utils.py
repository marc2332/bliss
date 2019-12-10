# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import os
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus


def run_scan(scan, runasync=False):
    """
    :param bliss.scanning.scan.Scan scan:
    :param bool runasync: run in separate Greenlet
    :returns Greenlet or None:
    """
    for node in scan.acq_chain.nodes_list:
        if node.name == "lima_simulator":
            ctrl_params = node.ctrl_params
            ctrl_params["saving_format"] = "HDF5"
            ctrl_params["saving_frame_per_file"] = 3
            ctrl_params["saving_suffix"] = ".h5"
        elif node.name == "lima_simulator2":
            ctrl_params = node.ctrl_params
            ctrl_params["saving_format"] = "EDF"
            ctrl_params["saving_frame_per_file"] = 3
            ctrl_params["saving_suffix"] = ".edf"
    if runasync:
        return gevent.spawn(scan.run)
    else:
        return scan.run()


class TimeOutError(Exception):
    pass


def wait_scan_data_finished(scans, config=True, timeout=20, writer_stdout=None):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    :param int timeout:
    :param io.BufferedIOBase writer_stdout: prints this on timeout
    """
    uris = [scan_utils.scan_uri(scan, subscan=1, config=config) for scan in scans]
    try:
        with gevent.Timeout(timeout, TimeOutError):
            while uris:
                uris = [uri for uri in uris if not nexus.nxComplete(uri)]
                gevent.sleep(0.1)
    except TimeOutError:
        # _terminate_writer()
        if writer_stdout is not None:
            print_output(writer_stdout)
        assert not uris, uris


def _terminate_writer():
    """
    This is a temporary fix when HDF5 files appear not updated.
    Not sure yet what causes this.
    """
    import psutil

    for proc in psutil.process_iter():
        if "nexus_writer_" in str(proc.cmdline()):
            proc.kill()
            # proc.wait()


def wait_scan_data_exists(scans, config=True, timeout=120):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    filenames = []
    for scan in scans:
        filenames += scan_utils.scan_filenames(scan, config=config)
    try:
        with gevent.Timeout(timeout, TimeOutError):
            while filenames:
                filenames = [f for f in filenames if not os.path.exists(f)]
                gevent.sleep(1)
    except TimeOutError:
        assert not filenames, filenames


def assert_scan_data_finished(scans, config=True):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    for scan in scans:
        uri = scan_utils.scan_uri(scan, subscan=1, config=config)
        nexus.nxComplete(uri)


def assert_scan_data_exists(scan, config=True):
    """
    :param bliss.scanning.scan.Scan scan:
    :param bool config: configurable writer
    """
    for filename in scan_utils.scan_filenames(scan, config=config):
        assert os.path.isfile(filename), filename


def open_data(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    scan_utils.open_data(scan, block=True)


def buffer_output(buffer):
    """
    :param io.BufferedIOBase buffer:
    :returns bytes:
    """
    out = b""
    with gevent.Timeout(1, RuntimeError("IO buffer is empty")):
        while True:
            try:
                out += buffer.read1()
            except RuntimeError:
                break
    return out


def print_output(buffer):
    """
    :param io.BufferedIOBase buffer:
    """
    for line in buffer_output(buffer).split(b"\n"):
        print(line.decode())
