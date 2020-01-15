# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from gevent import subprocess
import os
import sys
import functools
import traceback
from contextlib import contextmanager
from silx.io.dictdump import h5todict
from bliss.data.scan import watch_session_scans
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus
from nexus_writer_service.utils.process_utils import log_file_processes
from nexus_writer_service.io.io_utils import close_files
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
        except Exception as e:
            print("\nSCAN FAILED: " + str(s))
            traceback.print_exc()
            failed += 1
    assert not failed, "{}/{} scans failed".format(failed, len(scans))


class TimeOutError(Exception):
    pass


def _scan_uris(scans, config=True):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :returns list:
    """
    uris = []
    for scan in scans:
        uris += scan_utils.scan_uris(scan, config=config)
    assert uris
    return uris


def wait_scan_data_finished(scans, config=True, timeout=10, writer=None, **kwargs):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    :param num timeout:
    :param PopenGreenlet writer: writer process
    :param int timeout:
    """
    uris = _scan_uris(scans, config=config)
    # print("wait_scan_data_finished: {}".format(uris))
    try:
        with gevent.Timeout(timeout, TimeOutError):
            while uris:
                uris = [uri for uri in uris if not nexus.nxComplete(uri)]
                gevent.sleep(0.1)
    except TimeOutError:
        on_timeout(writer, uris)


def wait_scan_data_exists(scans, config=True, timeout=60, writer=None, **kwargs):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    uris = _scan_uris(scans, config=config)
    # print("wait_scan_data_exists: {}".format(filenames))
    try:
        with gevent.Timeout(timeout, TimeOutError):
            while uris:
                uris = [uri for uri in uris if not nexus.exists(uri)]
                gevent.sleep(0.1)
    except TimeOutError:
        on_timeout(writer, uris)


def assert_scan_data_not_corrupt(scans, config=True, **kwargs):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    filenames = []
    for scan in scans:
        # Only check the main data file, not the masters
        filenames.append(scan_utils.scan_filenames(scan, config=config)[0])
    for filename in filenames:
        try:
            h5todict(filename)
        except Exception:
            raise AssertionError(filename)


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


def assert_scan_data_finished(scans, config=True, **kwargs):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    uris = _scan_uris(scans, config=config)
    for uri in uris:
        nexus.nxComplete(uri)


def assert_scan_data_exists(scans, config=True, **kwargs):
    """
    :param list(bliss.scanning.scan.Scan) scans:
    :param bool config: configurable writer
    """
    uris = _scan_uris(scans, config=config)
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

    def print_stdout(self, file=None, **kwargs):
        if self.process is None or self.process.stdout is None:
            return
        if file is None:
            kwargs["file"] = sys.stdout
        else:
            kwargs["file"] = file
        print("\n### Test's subprocess {} stdout:".format(self.process.pid), **kwargs)
        for line in self.iter_stdout_lines():
            print(line, **kwargs)
        print("\n### END PROCESS STDOUT\n", **kwargs)

    def print_stderr(self, file=None, **kwargs):
        if self.process is None or self.process.stderr is None:
            return
        if file is None:
            kwargs["file"] = sys.stderr
        else:
            kwargs["file"] = file
        print("\n### Test's subprocess {} stderr:".format(self.process.pid), **kwargs)
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
    except Exception:
        process.print()
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
    except Exception:
        if process is not None:
            process.print_stdout()
        raise


def writer_stdout_on_exception(func):
    @functools.wraps(func)
    def inner(*args, **kwargs):
        writer = kwargs.get("writer", None)
        with stdout_on_exception(writer):
            func(*args, **kwargs)

    return inner


def nullhandler(*args):
    pass


class ScanWatcher:
    def __init__(
        self,
        session_name,
        new_scan=nullhandler,
        new_child=nullhandler,
        new_data=nullhandler,
        end_scan=nullhandler,
    ):
        self.session_name = session_name
        self.new_scan = new_scan  # args: scan_info
        self.new_child = new_child  # args: scan_info, node
        self.new_data = (
            new_data
        )  # args:  str(0d,1d,...), dict(master from scan_info's acq. chain), dict(...)
        self.end_scan = end_scan  # scan_info
        self._wakeup_read = None
        self._wakeup_write = None
        self.end_scan_event = gevent.event.Event()
        self.ready_event = gevent.event.Event()
        self.reset()

    def reset(self):
        self.end_scan_args = []
        self.end_scan_event.clear()
        self.ready_event.clear()
        close_files(self._wakeup_read, self._wakeup_write)

    def stop(self):
        os.write(self._wakeup_write, b"stop")

    def start(self, ready_timeout=3):
        self.reset()

        def end(*args):
            self.end_scan_event.set()
            self.end_scan_args.append(args)

        self._wakeup_read, self._wakeup_write = os.pipe()

        session_watcher = gevent.spawn(
            watch_session_scans,
            self.session_name,
            self.new_scan,
            self.new_child,
            self.new_data,
            scan_end_callback=end,
            ready_event=self.ready_event,
            exit_read_fd=self._wakeup_read,
        )

        self.ready_event.wait(timeout=ready_timeout)
        return session_watcher

    @contextmanager
    def watchscan(self, ready_timeout=3):
        try:
            session_watcher = self.start(ready_timeout=ready_timeout)
            try:
                yield self.end_scan_event
            finally:
                self.stop()
                try:
                    session_watcher.join(ready_timeout)
                except gevent.Timeout:
                    session_watcher.kill()
                    session_watcher.join()
        finally:
            self.reset()
