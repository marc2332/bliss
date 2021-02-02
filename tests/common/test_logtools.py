# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import logging
import re
import os
import gevent

from bliss.common.logtools import Log, get_logger, set_log_format, hexify
from bliss.common.logtools import log_debug, log_debug_data, log_error
from bliss.common.logtools import user_print, disable_user_output
from bliss import logging_startup
from bliss.shell.standard import debugon, debugoff
from bliss.common.mapping import Map, map_id
from bliss import global_map
import bliss
from bliss.common import scans
from bliss.common import plot


@pytest.fixture
def map():
    """
    Creates a new graph
    """
    map = Map()

    return map


@pytest.fixture
def params(beacon, map, log_context):
    """
    Creates a new beacon and log instance
    """
    # Save the logging context
    old_handlers = list(logging.getLogger().handlers)
    old_logger_dict = dict(logging.getLogger().manager.loggerDict)

    logging_startup()
    log = Log(map=map)

    yield beacon, log


class MappedController:

    name = "mc"

    def __init__(self, name="mc", parents_list=None, children_list=None):
        self.name = name
        global_map.register(self, parents_list, children_list)

    def msg_debug(self, msg=""):
        log_debug(self, "Debug message %s", msg)

    def msg_debug_data(self, msg=""):
        log_debug_data(self, "Debug data message %s", msg, b"asdasdadsa")

    def msg_info(self, msg=""):
        log_info(self, "Info message %s", msg)

    def msg_error(self, msg=""):
        log_error(self, "Error message %s", msg)


class Device:
    """
    Device for Logging Test
    """

    def __init__(self, name="", parents_list=None, children_list=None):
        self.name = name
        global_map.register(self, parents_list, children_list)


def test_bare_system(params):
    all_loggers = logging.getLogger().manager.loggerDict
    names = ["global", "global.controllers"]
    for name in names:
        assert name in all_loggers.keys()


def test_add_motor_m0(params):
    beacon, log = params
    m0 = beacon.get("m0")  # creating a device

    # Check if _logger appended to instance
    assert isinstance(get_logger(m0), logging.Logger)

    all_loggers = logging.getLogger().manager.loggerDict
    assert f"global.controllers.{m0.controller.name}.m0" in all_loggers.keys()


def test_m0_logger_debugon(params, caplog):
    """
    test the use of device's  debugon
    """
    beacon, log = params
    msg = "DEBUG TEST MESSAGE"

    m0 = beacon.get("m0")  # creating a device
    debugon(m0)
    assert get_logger(m0).level == logging.DEBUG
    log_debug(m0, msg)
    assert msg in caplog.text


def test_m0_logger_debugoff(params, caplog):
    """
    test the use of device's debugoff
    """
    beacon, log = params
    msg = "DEBUG TEST MESSAGE"

    m0 = beacon.get("m0")  # creating a device
    debugoff(m0)
    assert get_logger(m0).level == logging.NOTSET
    log_debug(m0, msg)
    assert msg not in caplog.text


def test_m0_debug_data_hex(params, caplog):
    """
    test the use of hex formatting
    """
    beacon, log = params
    expected = r"\xf4\xf3\xf2"

    m0 = beacon.get("m0")  # creating a device
    data = bytes([244, 243, 242]).decode("latin-1")
    assert hexify(data) == get_logger(m0).log_format_hex(data) == expected
    debugon(m0)
    set_log_format(m0, "hex")
    log_debug_data(m0, "debugging", data)

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
    assert get_logger(m0).log_format_ascii(data) == expected
    debugon(m0)
    set_log_format(m0, "ascii")
    log_debug_data(m0, "debugging", data)

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
    debugon(m0)
    log_debug_data(m0, msg, data)
    assert expected in caplog.text


def test_m0_logger_debug_data_other_types(params, caplog):
    beacon, log = params
    m0 = beacon.get("m0")  # creating a device
    debugon(m0)
    log_debug_data(m0, "INTEGER", 1234)
    log_debug_data(m0, "STRING", "toto")
    assert "INTEGER 1234" in caplog.text
    assert "STRING bytes=4 toto" in caplog.text


def test_standard_debugon_debugoff(params):
    beacon, log = params

    roby = beacon.get("roby")

    debugon(roby)

    assert get_logger(roby).level == logging.DEBUG

    debugoff(roby)

    assert get_logger(roby).level == logging.NOTSET

    debugon("*roby")

    assert get_logger(roby).level == logging.DEBUG

    debugoff("*roby")

    assert get_logger(roby).level == logging.NOTSET
    assert get_logger(roby).getEffectiveLevel() == logging.WARNING


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
        debugon(child)
        child.msg_debug(dbg_msg)
        child.msg_error(err_msg)
        assert dbg_msg in caplog.text
        assert err_msg in caplog.text
        caplog.clear()
        debugoff(child)
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
    d1 = Device(r"Hi_*2^a.o@@-[200]")
    assert map_id(d1) in global_map
    get_logger(d1)
    assert (
        global_map[map_id(d1)]["_logger"].name == "global.controllers.Hi__2_a_o__-[200]"
    )
    d2 = Device(r"/`/deviceDEVICE=+{}()")
    assert map_id(d2) in global_map
    get_logger(d2)
    assert (
        global_map[map_id(d2)]["_logger"].name
        == "global.controllers./_/deviceDEVICE=___()"
    )


def test_level_switch(params, caplog):
    """
    When we change the level manually with a value
    different than WARNING, this should toggle properly with
    debugon/debugoff
    """
    beacon, log = params
    m0 = beacon.get("m0")
    assert get_logger(m0).level == logging.NOTSET
    assert get_logger(m0).getEffectiveLevel() == logging.WARNING
    debugon(m0)
    assert get_logger(m0).level == logging.DEBUG
    assert get_logger(m0).getEffectiveLevel() == logging.DEBUG
    debugon(m0)  # repeat twice for replicate bug
    assert get_logger(m0).level == logging.DEBUG
    assert get_logger(m0).getEffectiveLevel() == logging.DEBUG
    get_logger(m0).debugoff()
    assert get_logger(m0).level == logging.NOTSET
    assert get_logger(m0).getEffectiveLevel() == logging.WARNING
    # this will change also the default level
    get_logger(m0).setLevel(logging.INFO)
    get_logger(m0).debugon()
    get_logger(m0).debugoff()
    assert get_logger(m0).level == logging.INFO
    assert get_logger(m0).getEffectiveLevel() == logging.INFO


def test_lslog(capsys, session, params):
    """Check that there is no repetition of same logger"""
    session.env_dict["lslog"]()
    captured = capsys.readouterr()
    text = str(captured.out)
    assert "bliss " in text
    assert text.count("global.controllers ") == 1


def test_user_print(capsys, log_shell_mode):
    string = "this is a test"
    user_print(string)
    captured = capsys.readouterr().out
    assert captured == string + "\n"


def test_user_print_no_end(capsys, log_shell_mode):
    user_print("my", end="", flush=False)
    user_print("test")
    captured = capsys.readouterr().out
    assert captured == "mytest\n"


def test_user_print_no_sep(capsys, log_shell_mode):
    text_list = "this is a test".split()
    user_print(*text_list, sep=":")
    captured = capsys.readouterr().out
    assert captured == ":".join(text_list) + "\n"


def test_user_print_disable(capsys, log_shell_mode):
    with disable_user_output():
        user_print("something")
    assert capsys.readouterr().out == ""


def test_nested_user_print_disable(capsys, log_shell_mode):
    with disable_user_output():
        with disable_user_output():
            user_print("something")
        user_print("should not appear")
    assert capsys.readouterr().out == ""


def test_user_print_greenlet(capsys, log_shell_mode):
    def greenlet1():
        with disable_user_output():
            gevent.sleep(.01)

    def greenlet2():
        user_print("showme")

    # gevent.sleep gives control to greenlet2
    gevent.joinall([gevent.spawn(g) for g in (greenlet1, greenlet2)])

    captured = capsys.readouterr().out
    assert captured == "showme\n"

    def greenlet3():
        with disable_user_output():
            gevent.sleep(.1)
            greenlet2()

    # inside disable_user_output no message should show
    gevent.joinall([gevent.spawn(g) for g in [greenlet3]])
    captured = capsys.readouterr().out
    assert captured == ""

    def greenlet3():
        gevent.sleep(.01)
        gevent.spawn(greenlet2)

    def greenlet4():
        gevent.sleep(.01)
        user_print("invisible")

    def greenlet5():
        with disable_user_output():
            greenlet4()

    gevent.joinall([gevent.spawn(g) for g in (greenlet5, greenlet3)])

    captured = capsys.readouterr().out
    assert captured == "showme\n"


def test_user_print_disable_scan(default_session, capsys, log_shell_mode):
    roby = default_session.config.get("roby")
    diode = default_session.config.get("diode")
    scans.ascan(roby, 0, 10, 3, .1, diode)
    captured = capsys.readouterr().out
    assert captured == ""


def test_user_print_disable_scan_calc_mot(default_session, capsys, log_shell_mode):
    s1vg = default_session.config.get("s1vg")
    diode = default_session.config.get("diode")
    scans.ascan(s1vg, 0, 1, 3, .1, diode)
    captured = capsys.readouterr().out
    assert captured == ""


def test_tango_devproxy_log_on_method(wago_tango_server, caplog):
    device_fqdn, dev_proxy = wago_tango_server

    debugon(dev_proxy)
    dev_proxy.turnon()
    assert "call" in caplog.text
    assert "returned" in caplog.text
    debugoff(dev_proxy)


def test_lima_devproxy_logger(default_session, lima_simulator, capsys, caplog):
    # be sure to activate 4 loggers
    lima = default_session.config.get("lima_simulator")
    lima.__info__()  # this is to register ROI counters on map
    lima.camera  # this is to register the camera on map

    # the following should not produce log messages (debug is off)
    val = lima.proxy.acq_expo_time
    assert caplog.text == ""

    # now activate debug and check 4 active loggers
    debugon(lima)
    captured = capsys.readouterr().out
    assert len(captured.strip().split("\n")) == 6

    # check some log messages for attribute get/set
    val = lima.proxy.acq_expo_time
    assert "getting attribute 'acq_expo_time':" in caplog.text
    new_val = val + 1
    lima.proxy.acq_expo_time = new_val
    assert "setting attribute 'acq_expo_time':" in caplog.text
    assert (lima.proxy.acq_expo_time) == new_val

    # test method call
    lima.proxy.set_timeout_millis(10)
    assert "call set_timeout_millis(10,)" in caplog.text
    debugoff(lima)


def test_log_server(session, log_directory, log_context):
    logging.getLogger("user_input").info("TEST USER INPUT LOGGER")
    logging.getLogger("exceptions").info("TEST EXCEPTION LOGGER")
    gevent.sleep(1)  # ensure log is written
    with open(os.path.join(log_directory, session.name + ".log"), "r") as logfile:
        l = logfile.readline()
        assert "TEST USER INPUT" in l
        l = logfile.readline()
        assert "TEST EXCEPTION" in l


def test_log_server__flint(test_session_with_flint, log_directory, log_context):
    session = test_session_with_flint
    flint = plot.get_flint()
    flint.test_log_error("TEST FLINT LOGGED ERROR")
    gevent.sleep(1)  # ensure log is written
    with open(os.path.join(log_directory, f"flint_{session.name}.log"), "r") as logfile:
        blob = logfile.read()
        assert "TEST FLINT LOGGED ERROR" in blob
