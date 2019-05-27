# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import logging
import re

from bliss.common.logtools import map_update_loggers, Log, LogMixin
from bliss.common.standard import debugon, debugoff
from bliss.common.mapping import Map
from bliss.common import session
import bliss


@pytest.fixture
def map():
    """
    Creates a new graph
    """
    map = Map()

    return map


@pytest.fixture
def params(beacon, map):
    """
    Creates a new beacon and log instance
    """
    logging.basicConfig(level=logging.WARNING)

    log = Log(map=map)

    return beacon, log


class NotMappedController(LogMixin):
    """
    Logging on this device should raise an exception as is not mapped
    """

    name = "nmc"

    def msg_debug(self):
        self._logger.debug("Debug message")

    def msg_debug_data(self):
        self._logger.debug_data("Debug message", b"asdasdadsa")

    def msg_info(self):
        self._logger.info("Info message")


class MappedController(NotMappedController, LogMixin):
    """
    Logging on this device should succeed
    """

    name = "mc"

    def __init__(self):
        session.get_current().map.register(self)


def test_bare_system(params):
    all_loggers = logging.getLogger().manager.loggerDict
    names = ["session", "session.controllers"]
    for name in names:
        assert name in all_loggers.keys()


def test_add_motor_m0(params):
    beacon, log = params
    m0 = beacon.get("m0")  # creating a device

    # Check if _logger appended to instance
    assert isinstance(m0._logger, logging.Logger)

    all_loggers = logging.getLogger().manager.loggerDict
    assert (
        f"session.controllers.{m0.controller.__class__.__name__}.m0"
        in all_loggers.keys()
    )


def test_m0_logger_debugon(params, caplog):
    """
    test the use of device's self._logger
    """
    beacon, log = params
    msg = "DEBUG TEST MESSAGE"

    m0 = beacon.get("m0")  # creating a device
    m0._logger.debugon()
    assert m0._logger.level == logging.DEBUG
    m0._logger.debug(msg)
    assert msg in caplog.text


def test_m0_logger_debugoff(params, caplog):
    """
    test the use of device's self._logger
    """
    beacon, log = params
    msg = "DEBUG TEST MESSAGE"

    m0 = beacon.get("m0")  # creating a device
    m0._logger.debugoff()
    assert m0._logger.level == logging.NOTSET
    m0._logger.debug(msg)
    assert msg not in caplog.text


def test_m0_debug_data_hex(params, caplog):
    """
    test the use of hex formatting
    """
    beacon, log = params
    expected = r"\xf4\xf3\xf2"

    m0 = beacon.get("m0")  # creating a device
    data = bytes([244, 243, 242]).decode("latin-1")
    assert m0._logger.log_format_hex(data) == expected
    m0._logger.debugon()
    m0._logger.set_hex_format()
    m0._logger.debug_data("debugging", data)

    assert expected in caplog.text
    assert "debugging" in caplog.text
    assert "bytes=3" in caplog.text


def test_m0_debug_data_ascii(params, caplog):
    """
    test the use of ascii formatting
    """
    beacon, log = params
    expected = r"ab\xf4\xf3\xf2"

    m0 = beacon.get("m0")  # creating a device
    data = bytes([97, 98, 244, 243, 242]).decode("latin-1")
    assert m0._logger.log_format_ascii(data) == expected
    m0._logger.debugon()
    m0._logger.set_ascii_format()
    m0._logger.debug_data("debugging", data)

    assert expected in caplog.text
    assert "debugging" in caplog.text
    assert "bytes=5" in caplog.text


def test_m0_logger_debug_data_dict(params, caplog):
    """
    test the use of debug_data with dict
    """
    beacon, log = params
    msg = "DEBUG TEST MESSAGE"
    data = {"important": 23, "even more": 92, 52: "y", 53: False, 54: None}
    expected = (
        "DEBUG TEST MESSAGE important=23 ; even more=92 ; 52=y ; 53=False ; 54=None"
    )

    m0 = beacon.get("m0")  # creating a device
    m0._logger.debugon()
    m0._logger.debug_data(msg, data)
    assert expected in caplog.text


def test_LogMixin(params, caplog):
    """
    Testing LogMixin on two classes
    """
    beacon, log = params

    nmc = NotMappedController()
    assert nmc._logger.name == "session.controllers.nmc"
    mc = MappedController()
    assert mc._logger.name == "session.controllers.mc"

    mc._logger.debugon()  # activates debug logging level
    expected = "Debug message"
    mc.msg_debug()
    assert expected in caplog.text

    expected = "Debug message"
    mc.msg_debug_data()
    assert expected in caplog.text

    expected = "Info message"
    mc.msg_info()
    assert expected in caplog.text

    assert hasattr(mc._logger, "debug_data")


def test_standard_debugon_debugoff(session):
    roby = session.config.get("roby")

    debugon(roby)

    assert roby._logger.level == logging.DEBUG

    debugoff(roby)

    assert roby._logger.level == logging.NOTSET

    debugon("*roby")

    assert roby._logger.level == logging.DEBUG

    debugoff("*roby")

    assert roby._logger.level == logging.NOTSET
    assert roby._logger.getEffectiveLevel() == logging.WARNING
