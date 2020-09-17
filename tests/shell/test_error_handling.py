# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.shell.cli import repl
from bliss.common import logtools


@pytest.fixture
def error_report():
    error_report = repl.install_excepthook()
    try:
        yield error_report
    finally:
        repl.reset_excepthook()


def test_error_report(error_report):
    errors = error_report._last_error.errors
    assert len(errors) == 0
    MYERROR = "MYERROR"

    def raise_exception():
        raise RuntimeError(MYERROR)

    def raise_hub_exception(nerrors=1):
        w = gevent.get_hub().loop.async_()
        w.start(raise_exception)
        n = len(errors) + nerrors
        try:
            w.send()
            with gevent.Timeout(10):
                while len(errors) != n:
                    gevent.sleep(0.1)
        finally:
            w.stop()
            w.close()

    # Exception in greenlet
    MYERROR = "MYERROR1"
    gevent.spawn(raise_exception).join()
    assert len(errors) == 1
    assert f"RuntimeError: {MYERROR}" in errors[-1]

    # Exception in gevent loop callback
    MYERROR = "MYERROR2"
    raise_hub_exception()
    assert len(errors) == 2
    assert f"RuntimeError: {MYERROR}" in errors[-1]

    logtools.logbook_on = True

    try:
        # Exception in greenlet
        MYERROR = "MYERROR3"
        gevent.spawn(raise_exception).join()
        assert len(errors) == 4
        assert f"RuntimeError: {MYERROR}" in errors[-2]
        assert "send_to_elogbook" in errors[-1]

        # Exception in gevent loop callback
        MYERROR = "MYERROR4"
        raise_hub_exception(2)
        assert len(errors) == 6
        assert f"RuntimeError: {MYERROR}" in errors[-2]
        assert "send_to_elogbook" in errors[-1]
    finally:
        logtools.logbook_on = False


def test_error_report_chained(error_report):
    errors = error_report._last_error.errors

    def func1():
        raise RuntimeError("LEVEL 0")

    def func2():
        try:
            func1()
        except Exception as e:
            raise RuntimeError("LEVEL 1") from e

    gevent.spawn(func2).join()

    assert len(errors) == 1
    assert "\nRuntimeError: LEVEL 0" in errors[0]
    assert "\nRuntimeError: LEVEL 1" in errors[0]
