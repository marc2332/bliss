# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


def test_get_custom_methods_list(robz):
    assert robz.custom_methods_list == [
        ("Set_Closed_Loop", ("bool", "None")),
        ("custom_command_no_types", (None, None)),
        ("custom_get_chapi", ("str", "str")),
        ("custom_get_forty_two", ("None", "int")),
        ("CustomGetTwice", ("int", "int")),
        ("custom_park", (None, None)),
        ("custom_send_command", ("str", "None")),
        ("custom_set_measured_noise", ("float", "None")),
        ("generate_error", (None, None)),
        ("get_cust_attr_float", ("None", "float")),
        ("get_voltage", ("None", "int")),
        ("set_cust_attr_float", ("float", "None")),
        ("set_voltage", ("int", "None")),
    ]


def test_custom_park(robz):
    assert robz.custom_park() is None


def test_custom_get_forty_two(robz):
    assert robz.custom_get_forty_two() == 42


def test_custom_get_twice(robz):
    assert robz.CustomGetTwice(42) == 84


def test_custom_get_chapi(robz):
    assert robz.custom_get_chapi("chapi") == "chapo"
    assert robz.custom_get_chapi("titi") == "toto"
    assert robz.custom_get_chapi("roooh") == "bla"


def test_custom_send_command(robz):
    assert robz.custom_send_command("SALUT sent") is None
