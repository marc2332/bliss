# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import gevent
import pytest
import nxw_test_data
import nxw_test_utils
from louie import dispatcher
from bliss.common import scans
from nexus_writer_service.utils import scan_utils
from nexus_writer_service.io import nexus


def test_nxw_readers(nexus_writer_config):
    _test_nxw_readers(mode="r", enable_file_locking=False, **nexus_writer_config)


def test_nxw_readers_lock(nexus_writer_config):
    _test_nxw_readers(mode="r", enable_file_locking=True, **nexus_writer_config)


def test_nxw_readers_append(nexus_writer_config):
    _test_nxw_readers(mode="a", enable_file_locking=False, **nexus_writer_config)


def test_nxw_readers_appendlock(nexus_writer_config):
    _test_nxw_readers(mode="a", enable_file_locking=True, **nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_readers(
    mode="r",
    enable_file_locking=False,
    session=None,
    tmpdir=None,
    writer=None,
    config=True,
    **kwargs
):
    session.scan_saving.technique = "none"
    filename = scan_utils.session_filename(scan_saving=session.scan_saving)
    with nexus.nxRoot(filename, mode="a") as nxroot:
        nxentry = nexus.nxEntry(nxroot, "dummy")
        measurement = nexus.nxCollection(nxentry, "measurement")
        measurement["a"] = list(range(10))
        measurement["b"] = list(range(10))
    startevent = gevent.event.Event()
    readerkwargs = {"mode": mode, "enable_file_locking": enable_file_locking}
    readers = [
        gevent.spawn(reader, filename, startevent, hold=i == 0, **readerkwargs)
        for i in range(4)
    ]
    startevent.wait()
    reset_dispatcher = False
    try:
        detector = "diode3"
        if mode == "a" and not enable_file_locking:
            # Readers will not crash the scan (not sure why) but corrupt the file
            scan_shape = (100,)
            scan = scans.loopscan(
                scan_shape[0], .1, session.env_dict[detector], run=False
            )
            nxw_test_utils.run_scan(scan)
            gevent.killall(readers)
            gevent.joinall(readers)
            readers = []
            with pytest.raises(AssertionError):
                # We can only detect the corruption after closing the readers
                nxw_test_utils.assert_scan_data_not_corrupt([scan])
        elif enable_file_locking:
            # Readers will crash the scan but not corrupt the file
            reset_dispatcher = True
            scan = scans.timescan(.1, session.env_dict[detector], run=False)
            with gevent.Timeout(10):
                with pytest.raises(RuntimeError):
                    nxw_test_utils.run_scan(scan)
            gevent.killall(readers)
            gevent.joinall(readers)
            readers = []
            nxw_test_utils.assert_scan_data_not_corrupt([scan])
        else:
            # Neither scan nor file are disturbed by these readers
            scan_shape = (100,)
            scan = scans.loopscan(
                scan_shape[0], .1, session.env_dict[detector], run=False
            )
            nxw_test_utils.run_scan(scan)
            gevent.killall(readers)
            gevent.joinall(readers)
            readers = []
            nxw_test_utils.wait_scan_data_exists([scan], writer=writer)
            nxw_test_utils.assert_scan_data_not_corrupt([scan])
            nxw_test_data.assert_scan_data(
                scan,
                scan_shape=scan_shape,
                positioners=[["elapsed_time", "epoch"]],
                detectors=[detector],
                **kwargs
            )
    finally:
        if reset_dispatcher:
            dispatcher.reset()
        if readers:
            gevent.killall(readers)
            gevent.joinall(readers)


def reader(filename, startevent, hold=False, **kwargs):
    """This reader opens in different modes but only performs reading operations.
    """
    while True:
        gevent.sleep(0.1)
        try:
            with nexus.File(filename, **kwargs) as f:
                startevent.set()
                while True:
                    gevent.sleep(0.1)
                    try:
                        for entry in f:
                            list(f[entry]["instrument"].keys())
                            list(f[entry]["measurement"].keys())
                    except BaseException:
                        pass
                    finally:
                        if not hold:
                            break
        except (KeyboardInterrupt, gevent.GreenletExit):
            break
        except BaseException:
            pass
