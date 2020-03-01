# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from gevent import subprocess
import sys
import functools
import traceback
import random
from contextlib import contextmanager
from silx.io.dictdump import h5todict
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus
from nexus_writer_service.utils.process_utils import log_file_processes
from nexus_writer_service.utils.logging_utils import print_err


def run_scan(scan, runasync=False):
    """
    :param bliss.scanning.scan.Scan scan:
    :param bool runasync: run in separate Greenlet
    :returns Greenlet or None:
    """
    for node in scan.acq_chain.nodes_list:
        if node.name == "lima_simulator":
            ctrl_params = node.ctrl_params
            saving_format = random.choice(["HDF5", "HDF5GZ"])
            ctrl_params["saving_format"] = saving_format
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


def assert_async_scans_success(scans, greenlets):
    """
    :param list(bliss.scanning.scan.Scan) scan:
    :param list(gevent.Greenlet) as greenlets:
    :raises AssertionError:
    """
    gevent.joinall(greenlets)
    failed = 0
    for g, s in zip(greenlets, scans):
        try:
            g.get()
        except BaseException as e:
            print("\nSCAN FAILED: " + str(s))
            traceback.print_exc()
            failed += 1
    assert not failed, "{}/{} scans failed".format(failed, len(scans))


def _scan_uris(scans):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :returns list:
    """
    uris = []
    for scan in scans:
        uris += scan_utils.scan_uris(scan)
    assert uris
    return uris


def wait_scan_data_finished(scans, timeout=10, writer=None):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param PopenGreenlet writer: writer process
    :param num timeout:
    :param int timeout:
    """
    uris = _scan_uris(scans)
    # print("wait_scan_data_finished: {}".format(uris))
    try:
        with gevent.Timeout(timeout):
            while uris:
                uris = [uri for uri in uris if not nexus.nxComplete(uri)]
                gevent.sleep(0.1)
    except gevent.Timeout:
        on_timeout(writer, uris)


def wait_scan_data_exists(scans, timeout=10, writer=None):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param PopenGreenlet writer: writer process
    """
    uris = _scan_uris(scans)
    # print("wait_scan_data_exists: {}".format(filenames))
    try:
        with gevent.Timeout(timeout):
            while uris:
                uris = [uri for uri in uris if not nexus.exists(uri)]
                gevent.sleep(0.1)
    except gevent.Timeout:
        on_timeout(writer, uris)


def assert_scan_data_not_corrupt(scans):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    """
    filenames = []
    for scan in scans:
        # Only check the main data file, not the masters
        filenames.append(scan_utils.scan_filename(scan))
    for filename in filenames:
        try:
            h5todict(filename)
        except Exception as e:
            raise AssertionError("Cannot read {}: {}".format(repr(filename), e))


def on_timeout(writer, uris):
    # The writer might still have the file open (which would be a bug)
    # writer.kill()
    # writer.join()
    # log_file_processes(print_err, r".+\.h5$")
    # log_file_processes(print_err, r".+\.edf$")
    for uri in uris:
        pattern = ".+{}$".format(nexus.splitUri(uri)[0])
        log_file_processes(print_err, pattern)
    assert not uris, uris


def assert_scan_data_finished(scans):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    uris = _scan_uris(scans)
    for uri in uris:
        nexus.nxComplete(uri)


def assert_scan_data_exists(scans):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    """
    uris = _scan_uris(scans)
    for uri in uris:
        assert nexus.exists(uri), uri


def open_data(scan):
    """
    :param bliss.scanning.scan.Scan scan:
    """
    scan_utils.open_data(scan, block=True)


class PopenGreenlet(gevent.Greenlet):
    """
    Run subprocess while purging the stdout and stderr pipes
    so they don't get full and block the subprocess.
    """

    def __init__(self, *popenargs, **popenkw):
        super(PopenGreenlet, self).__init__()
        self.process = None
        self.stdout = b""
        self.stderr = b""
        self.popenargs = popenargs
        self.popenkw = popenkw

    def _run(self):
        self.process = process = subprocess.Popen(*self.popenargs, **self.popenkw)
        try:
            while True:
                if process.stdout is not None:
                    self.stdout += process.stdout.read1()
                if process.stderr is not None:
                    self.stderr += process.stderr.read1()
                gevent.sleep()
        except gevent.GreenletExit:
            pass
        finally:
            self.process.terminate()
            # self.process.join()

    def __contains__(self, data):
        try:
            data = data.encode()
        except AttributeError:
            pass
        return data in self.stdout or data in self.stderr

    def stdout_contains(self, data):
        try:
            data = data.encode()
        except AttributeError:
            pass
        return data in self.stdout

    def stderr_contains(self, data):
        try:
            data = data.encode()
        except AttributeError:
            pass
        return data in self.stderr

    def iter_stdout_lines(self):
        for line in self.stdout.split(b"\n"):
            yield line.decode().rstrip()

    def iter_stderr_lines(self):
        for line in self.stderr.split(b"\n"):
            yield line.decode().rstrip()

    def print_stdout(self, reason=None, file=None, **kwargs):
        if self.process is None or self.process.stdout is None:
            return
        if file is None:
            kwargs["file"] = sys.stdout
        else:
            kwargs["file"] = file
        print(
            "\n### Test's subprocess {} stdout (Reason: {}):".format(
                self.process.pid, reason
            ),
            **kwargs
        )
        for line in self.iter_stdout_lines():
            print(line, **kwargs)
        print("\n### END PROCESS STDOUT\n", **kwargs)

    def print_stderr(self, reason=None, file=None, **kwargs):
        if self.process is None or self.process.stderr is None:
            return
        if file is None:
            kwargs["file"] = sys.stderr
        else:
            kwargs["file"] = file
        print(
            "\n### Test's subprocess {} stderr (Reason: {}):".format(
                self.process.pid, reason
            ),
            **kwargs
        )
        for line in self.iter_stderr_lines():
            print(line, **kwargs)
        print("\n### END PROCESS STDERR\n", **kwargs)

    def print(self, **kwargs):
        self.print_stdout(**kwargs)
        self.print_stderr(**kwargs)


@contextmanager
def popencontext(*popenargs, **popenkw):
    process = PopenGreenlet(*popenargs, **popenkw)
    process.start()
    try:
        yield process
    except BaseException as e:
        process.print(reason=str(e))
        raise
    finally:
        process.kill()


@contextmanager
def stdout_on_exception(process):
    """
    :param PopenGreenlet process:
    """
    try:
        yield
    except BaseException as e:
        if process is not None:
            process.print(reason=str(e))
        raise


def writer_stdout_on_exception(func):
    @functools.wraps(func)
    def inner(*args, **kwargs):
        writer = kwargs.get("writer", None)
        with stdout_on_exception(writer):
            func(*args, **kwargs)

    return inner
