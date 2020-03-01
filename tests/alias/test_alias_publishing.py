# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans


def test_alias_data_channel(alias_session):
    env_dict = alias_session.env_dict

    s = scans.a2scan(
        env_dict["robyy"],
        0,
        1,
        env_dict["robzz"],
        0,
        1,
        3,
        0.001,
        env_dict["simu1"].counters.spectrum_det0,
        env_dict["dtime"],
        env_dict["lima_simulator"].counters.r1_sum,  # has an alias 'myroi'
        env_dict["lima_simulator"].counters.r2_sum,
        env_dict["myroi3"],
        save=True,
        return_scan=True,
    )

    dump1 = """{a2scan}:axis:robyy robyy
{a2scan}:axis:robzz robzz
{a2scan}:axis:timer:elapsed_time elapsed_time
{a2scan}:axis:timer:epoch epoch
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi myroi
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_sum r2_sum
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi3 myroi3
{a2scan}:axis:timer:simu1:dtime dtime
{a2scan}:axis:timer:simu1:spectrum_det0 spectrum_det0""".format(
        a2scan=s.node.db_name
    ).split(
        "\n"
    )

    d = list()
    for n in s.node.iterator.walk(filter="channel", wait=False):
        assert " ".join([n.db_name, n.short_name]) in dump1


def test_alias_default_lima_counters(alias_session):
    env_dict = alias_session.env_dict

    s = scans.a2scan(
        env_dict["robyy"],
        0,
        1,
        env_dict["robzz"],
        0,
        1,
        3,
        0.001,
        env_dict["lima_simulator"],
        save=True,
    )

    dump1 = """{a2scan}:axis:robyy robyy
{a2scan}:axis:robzz robzz
{a2scan}:axis:timer:elapsed_time elapsed_time
{a2scan}:axis:timer:epoch epoch
{a2scan}:axis:timer:lima_simulator:image image
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_avg r1_avg
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_max r1_max
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_min r1_min
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_std r1_std
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi myroi
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_avg r2_avg
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_max r2_max
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_min r2_min
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_std r2_std
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_sum r2_sum
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_avg r3_avg
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_max r3_max
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_min r3_min
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_std r3_std
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi3 myroi3""".format(
        a2scan=s.node.db_name
    ).split(
        "\n"
    )

    d = list()
    for n in s.node.iterator.walk(filter="channel image", wait=False):
        assert " ".join([n.db_name, n.short_name]) in dump1


def test_lima_counter_aliased_and_lima_counters(alias_session):
    # related to https://gitlab.esrf.fr/bliss/bliss/merge_requests/1455#note_34525
    env_dict = alias_session.env_dict

    s = scans.a2scan(
        env_dict["robyy"],
        0,
        1,
        env_dict["robzz"],
        0,
        1,
        3,
        0.001,
        env_dict["myroi3"],
        env_dict["lima_simulator"],
        save=True,
    )

    dump1 = """{a2scan}:axis:robyy robyy
{a2scan}:axis:robzz robzz
{a2scan}:axis:timer:elapsed_time elapsed_time
{a2scan}:axis:timer:epoch epoch
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_avg r1_avg
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_max r1_max
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_min r1_min
{a2scan}:axis:timer:lima_simulator:roi_counters:r1_std r1_std
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi myroi
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_avg r2_avg
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_max r2_max
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_min r2_min
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_std r2_std
{a2scan}:axis:timer:lima_simulator:roi_counters:r2_sum r2_sum
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_avg r3_avg
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_max r3_max
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_min r3_min
{a2scan}:axis:timer:lima_simulator:roi_counters:r3_std r3_std
{a2scan}:axis:timer:lima_simulator:roi_counters:myroi3 myroi3"""
    dump1_str = dump1.format(a2scan=s.node.db_name)

    d = list()
    i = 0
    for n in s.node.iterator.walk(filter="channel", wait=False):
        print(" ".join([n.db_name, n.short_name]))
        assert " ".join([n.db_name, n.short_name]) in dump1_str
        i += 1
    assert i == len(dump1_str.split("\n"))
    s2 = scans.a2scan(
        env_dict["robyy"],
        0,
        1,
        env_dict["robzz"],
        0,
        1,
        3,
        0.001,
        env_dict["lima_simulator"],
        env_dict["myroi3"],
        save=True,
    )
    dump1_str = dump1.format(a2scan=s2.node.db_name)
    d = list()
    i = 0
    for n in s2.node.iterator.walk(filter="channel", wait=False):
        assert " ".join([n.db_name, n.short_name]) in dump1_str
        i += 1
    assert i == len(dump1_str.split("\n"))
