# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import logging
import re

from bliss.common.logtools import map_update_loggers, Log, LogMixin, logging_startup
from bliss.common.standard import debugon, debugoff, lslog
from bliss.common.mapping import Map, map_id
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
    logging_startup()

    log = Log(map=map)

    yield beacon, log

    logging.shutdown()
    logging.setLoggerClass(logging.Logger)
    logging.getLogger().handlers.clear()  # deletes all handlers
    logging.getLogger().manager.loggerDict.clear()  # deletes all loggers


class NotMappedController(LogMixin):
    """
    Logging on this device should raise an exception as is not mapped
    """

    name = "nmc"

    def __init__(self, name="nmc"):
        self.name = name

    def msg_debug(self, msg=""):
        self._logger.debug(f"Debug message {msg}")

    def msg_debug_data(self, msg=""):
        self._logger.debug_data(f"Debug message {msg}", b"asdasdadsa")

    def msg_info(self, msg=""):
        self._logger.info(f"Info message {msg}")

    def msg_error(self, msg=""):
        self._logger.error(f"Error message {msg}")


class MappedController(NotMappedController, LogMixin):
    """
    Logging on this device should succeed
    """

    def __init__(self, name="mc", parents_list=None, children_list=None):
        self.name = name
        session.get_current().map.register(self, parents_list, children_list)


class Device(LogMixin):
    """
    Device for Logging Test
    """

    def __init__(self, name="", parents_list=None, children_list=None):
        self.name = name
        session.get_current().map.register(self, parents_list, children_list)


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

    nmc = NotMappedController("nmc")
    assert nmc._logger.name == "session.controllers.nmc"
    mc = MappedController("mc")
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


def test_standard_debugon_debugoff(params):
    beacon, log = params

    roby = beacon.get("roby")

    debugon(roby)

    assert roby._logger.level == logging.DEBUG

    debugoff(roby)

    assert roby._logger.level == logging.NOTSET

    debugon("*roby")

    assert roby._logger.level == logging.DEBUG

    debugoff("*roby")

    assert roby._logger.level == logging.NOTSET
    assert roby._logger.getEffectiveLevel() == logging.WARNING


def node_check(obj, caplog, children=None):
    """
    Activate/deactivat debug for one parent node and recursively check
    that message on children are printed
    """
    if children is None:
        children = []
    # obj = locals()[name]
    for child in children:
        # for child in (locals()[obj_name] for  obj_name in children):
        dbg_msg = f"{child!r} debug"
        err_msg = f"{child!r} error"
        child.msg_debug(dbg_msg)
        child.msg_error(err_msg)
        assert dbg_msg not in caplog.text
        assert err_msg in caplog.text
        debugon(obj)  # debug at parent level should activate debug on child
        child.msg_debug(dbg_msg)
        assert dbg_msg in caplog.text
        debugoff(obj)
        caplog.clear()
        child.msg_debug(dbg_msg)
        child.msg_error(err_msg)
        assert dbg_msg not in caplog.text
        assert err_msg in caplog.text
        caplog.clear()

        # activate with _logger
        child._logger.debugon()
        child.msg_debug(dbg_msg)
        child.msg_error(err_msg)
        assert dbg_msg in caplog.text
        assert err_msg in caplog.text
        caplog.clear()
        child._logger.debugoff()
        child.msg_debug(dbg_msg)
        child.msg_error(err_msg)
        assert dbg_msg not in caplog.text
        assert err_msg in caplog.text
        caplog.clear()
        debugoff(obj)


def test_chain_devices_log(params, caplog):
    """
    Complex logging structure
    """
    # build the device tree
    # d1 -- d2 -- d3 -- d4 -- d5
    #    \- d6 -- d7 -- d8
    #          \- d9 -- d10
    #                \- d11
    d1 = MappedController("d1")
    d2 = MappedController("d2", parents_list=[d1])
    d3 = MappedController("d3", parents_list=[d2])
    d4 = MappedController("d4", parents_list=[d3])
    d5 = MappedController("d5", parents_list=[d4])
    d6 = MappedController("d6", parents_list=[d1])
    d7 = MappedController("d7", parents_list=[d6])
    d8 = MappedController("d8", parents_list=[d7])
    d9 = MappedController("d9", parents_list=[d6])
    d10 = MappedController("d10", parents_list=[d9])
    d11 = MappedController("d11", parents_list=[d9])

    node_check(d1, caplog, children=[d2, d3, d4, d5, d6, d7, d8, d9, d10, d11])
    node_check(d2, caplog, children=[d3, d4, d5])
    node_check(d6, caplog, children=[d7, d8, d9, d10, d11])


def test_log_name_sanitize(params):
    beacon, log = params
    m = session.get_current().map
    d1 = Device(r"Hi_*2^a.o@@-[200]")
    assert map_id(d1) in m
    assert m[map_id(d1)]["_logger"].name == "session.controllers.Hi__2_a_o__-[200]"
    d2 = Device(r"/`/deviceDEVICE=+{}()")
    assert map_id(d1) in m
    assert m[map_id(d2)]["_logger"].name == "session.controllers.___deviceDEVICE=___()"


def test_level_switch(params, caplog):
    """
    When we change the level manually with a value
    different than WARNING, this should toggle properly with
    debugon/debugoff
    """
    beacon, log = params
    m0 = beacon.get("m0")
    assert m0._logger.level == logging.NOTSET
    assert m0._logger.getEffectiveLevel() == logging.WARNING
    m0._logger.debugon()
    assert m0._logger.level == logging.DEBUG
    assert m0._logger.getEffectiveLevel() == logging.DEBUG
    m0._logger.debugon()  # repeat twice for replicate bug
    assert m0._logger.level == logging.DEBUG
    assert m0._logger.getEffectiveLevel() == logging.DEBUG
    m0._logger.debugoff()
    assert m0._logger.level == logging.NOTSET
    assert m0._logger.getEffectiveLevel() == logging.WARNING
    # this will change also the default level
    m0._logger.setLevel(logging.INFO)
    m0._logger.debugon()
    m0._logger.debugoff()
    assert m0._logger.level == logging.INFO
    assert m0._logger.getEffectiveLevel() == logging.INFO
