# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PI E-753 piezo controller hardware test.

Run with:
    $ pytest --axis-name <axis-name> ..../test_PI_E753.py

"""
import time
import pytest


@pytest.fixture
def axis(request, beacon_beamline):
    """
    Function to access axis given as parameter in test command line.
    """
    axis_name = request.config.getoption("--axis-name")
    test_axis = beacon_beamline.get(axis_name)
    try:
        yield test_axis
    finally:
        test_axis.controller.finalize()
        # time.sleep(1)


def test_hw_axis_init(axis):
    """
    Hardware initialization.
    Device must be present.
    Use axis fixture.
    """
    axis.sync_hard()
    axis.controller._initialize_axis(axis)


def test_hw_read_values(axis):
    """
    Read position (cache ?)
    """
    pos = axis.position
    # print(f"{axis.name} POSITION={pos}")
    # must be in closed-loop ?

    assert pos >= 0
    assert pos <= 100

    pos1 = axis.measured_position
    vol = axis.get_voltage()
    out_vol = axis.get_output_voltage()
    cl_st = axis.get_closed_loop()
    model = axis.get_model()

    ans = axis.controller.command("SPA? 1 0x07000000")
    ans = axis.controller.command("*IDN?")

    # Voltage Low Limit
    ans = axis.controller.command("SPA? 1 0x07000A00")

    # Voltage High Limit
    ans = axis.controller.command("SPA? 1 0x07000A01")

    pos2 = axis.controller._get_pos()

    axis_id = axis.controller.get_id(axis)
    axis_info = axis.controller.get_axis_info(axis)
    vel = axis.controller._get_velocity(axis)
    tg_pos = axis.controller._get_target_pos(axis)
    ont_status = axis.controller._get_on_target_status(axis)
    cl_status = axis.controller._get_closed_loop_status(axis)

    # Communication parameters
    com_pars = axis.controller.command("IFC?", 5)
    # Return: ['RSBAUD=115200 ', 'IPSTART=0 ', 'IPADR=192.168.2.100:50000 ',
    #          'IPMASK=255.255.255.0 ', 'MACADR=80:1F:12:E8:CE:A4']
    assert com_pars[0][:6] == "RSBAUD"
    assert com_pars[1][:7] == "IPSTART"
    assert com_pars[2][:5] == "IPADR"
    assert com_pars[3][:6] == "IPMASK"
    assert com_pars[4][:6] == "MACADR"

    # send 2 commands separated by "\n"
    pos, vel = axis.controller.command("POS? 1\nVEL? 1", 2)


def test_hw_get_info(axis):
    info_str1 = axis.get_info()
    # print(info_str1)

    info_str2 = axis.get_info()

    # Info strings have same length (with 1% accuracy).
    # This means that 2 consecutive reading seem correct.
    assert pytest.approx(len(info_str1), rel=0.01) == len(info_str2)


def test_hw_halt(axis):
    pos = axis.measured_position

    # STP
    axis.controller.sock.write(b"STP\r")
    err_no, err_desc = axis.controller.get_error()
    assert int(err_no) == 10

    # HLT command does not exist in e753.
    # ans = axis.controller.command("HLT 1")

    #  "#24"
    axis.controller.sock.write(chr(24).encode())
    err = axis.controller.get_error()
    # ERR=(10, 'Controller was stopped by command')

    # '#5' command requests motion status (only in closed-loop mode)
    # 1 2 4 : axis 1, 2, 3 is moving
    bit_status = axis.controller.sock.write_readline(chr(5).encode())

    pos = axis.measured_position
