# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import pytest
import gevent
import nxw_test_utils
from bliss.common import scans
from bliss.common.tango import DevFailed
from louie import dispatcher
from nexus_writer_service.utils.scan_utils import session_filename


def test_nxw_crash(nexus_writer_config):
    _test_nxw_crash(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_crash(session=None, **kwargs):
    if session.scan_saving.writer == "nexus":
        _test_tango(session=session, **kwargs)
    else:
        _test_process(session=session, **kwargs)


def _test_tango(session=None, tmpdir=None, writer=None, **kwargs):
    filename = session_filename(scan_saving=session.scan_saving)
    detector = session.env_dict["diode3"]
    _crash_scan_writer_greenlet(filename, detector)
    _crash_scan_writer_process(filename, detector, writer)


def _crash_scan_writer_greenlet(filename, detector):
    return  # TODO: does not work because scan writer holds the file open

    # Test crashing scan writer (only the greenlet)
    scan = scans.timescan(.1, detector, run=False)

    def crash_writer():
        while not os.path.exists(filename):
            gevent.sleep(1)
        gevent.sleep(5)
        os.chmod(filename, 0o544)

    greenlet = gevent.spawn(crash_writer)
    with gevent.Timeout(20):
        with pytest.raises(RuntimeError):
            scan.run()
    greenlet.join()
    try:
        os.remove(filename)
    except OSError:
        pass
    # TODO: no proper cleanup by Bliss
    dispatcher.reset()


def _crash_scan_writer_process(filename, detector, writer):
    # Test killing writer (kill tango server)
    scan = scans.timescan(.1, detector, run=False)

    def kill_writer():
        while not os.path.exists(filename):
            gevent.sleep(1)
        gevent.sleep(5)
        writer.kill()

    greenlet = gevent.spawn(kill_writer)
    with gevent.Timeout(20):
        with pytest.raises(DevFailed):
            scan.run()
    greenlet.join()
    try:
        os.remove(filename)
    except OSError:
        pass
    # TODO: no proper cleanup by Bliss
    dispatcher.reset()


def _test_process(session=None, tmpdir=None, writer=None, **kwargs):
    pytest.skip("No feedback of crashing writer in BLISS")
