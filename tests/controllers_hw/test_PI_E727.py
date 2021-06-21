# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PI E-727 piezo controller hardware test.

Run with:
    $ pytest --axis-name <axis-name> --axis-name2 <axis-name2>
             --axis-name3 <axis-name3> ..../test_PI_E727.py

  ex : pytest --axis-name pb2 --axis-name2 pt2 --axis-name3 pcam tests/controllers_hw/test_PI_E727.py

"""
import time
import pytest


@pytest.fixture
def axis(request, beacon_beamline):
    """
    Function to access axes given as parameter in test command line.
    """
    axis_list = list()

    try:
        axis_name = request.config.getoption("--axis-name")
        print("axis_name=", axis_name)
        test_axis = beacon_beamline.get(axis_name)
        # print("test_axis=", test_axis)
        axis_list.append(test_axis)
    except:
        print("cannot get", axis_name)

    try:
        axis_name2 = request.config.getoption("--axis-name2")
        print("axis_name2=", axis_name2)
        test_axis2 = beacon_beamline.get(axis_name2)
        axis_list.append(test_axis2)
    except:
        print("")

    try:
        axis_name3 = request.config.getoption("--axis-name3")
        print("axis_name3=", axis_name3)
        test_axis3 = beacon_beamline.get(axis_name3)
        axis_list.append(test_axis3)
    except:
        print("")

    if len(axis_list) > 0:
        # print("axis_list=", axis_list)
        try:
            yield axis_list
        finally:
            for axis in axis_list:
                axis.controller.close()


def test_hw_axis_init(axis):
    """
    Hardware initialization
    Device must be present.
    Use axis fixture.
    """

    for axis_test in axis:
        print(f"{axis_test.name} pos={axis_test.position}")
        axis_test.sync_hard()


def test_hw_read_position(axis):
    """
    Read measured position
    """

    for axis in axis:
        print(f"{axis.name}, measured_position={axis.measured_position}")


def test_hw_read_values(axis):
    """
    Read various parameters
    """
    print("test_hw_read_values")

    for axis in axis:
        print(axis.name)
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

        #        ans = axis.controller.command("SPA? 1 0x7000000")
        ans = axis.controller.command("*IDN?")

        # Voltage Low Limit
        #        ans = axis.controller.get_voltage_low_limit(axis)
        # Voltage High Limit
        #        ans = axis.controller.get_voltage_high_limit(axis)

        pos2 = axis.controller._get_pos(axis)

        axis_id = axis.controller.get_id(axis)
        axis_info = axis.controller.get_axis_info(axis)
        vel = axis.controller.read_velocity(axis)
        tg_pos = axis.controller._get_target_pos(axis)
        ont_status = axis.controller._get_on_target_status(axis)
        cl_status = axis.controller._get_closed_loop_status(axis)

        # send 2 commands separated by "\n"


#        pos, vel = axis.controller.command("POS? 1\nVEL? 1", nb_line=2)


def test_hw_get_info(axis):
    for axis in axis:
        info_str1 = axis.get_info()
        time.sleep(0.1)
        info_str2 = axis.get_info()
        # Info strings have same length (with 1% accuracy).
        # This means that 2 consecutive reading seem correct.
        assert pytest.approx(len(info_str1), rel=0.01) == len(info_str2)


# def test_hw_halt(axis):
#    pos = axis.measured_position
#
#    # STP
#    axis.controller.sock.write(b"STP\r")
#    err_no, err_desc = axis.controller.get_error()
#    assert int(err_no) == 10
#
#    # HLT command does not exist in e753.
#    # ans = axis.controller.command("HLT 1")
#
#    #  "#24"
#    axis.controller.sock.write(chr(24).encode())
#    err = axis.controller.get_error()
#    # ERR=(10, 'Controller was stopped by command')
#
#    # '#5' command requests motion status (only in closed-loop mode)
#    # 1 2 4 : axis 1, 2, 3 is moving
#    bit_status = axis.controller.sock.write_readline(chr(5).encode())
#
#    pos = axis.measured_position
