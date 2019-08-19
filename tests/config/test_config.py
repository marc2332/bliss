# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.conductor import client
from bliss.config.plugins.utils import replace_reference_by_object
import pytest
import sys, os


@pytest.mark.parametrize(
    "file_name, node_name, copy",
    [
        ["read_write.yml", "rw_test", False],
        ["read_write_2.yml", "rw_test_2", False],
        ["read_write.yml", "rw_test", True],
        ["read_write_2.yml", "rw_test_2", True],
    ],
)
def test_config_save(beacon, beacon_directory, file_name, node_name, copy):
    test_file_path = os.path.join(beacon_directory, file_name)
    rw_cfg = beacon.get_config(node_name)
    if copy:
        rw_cfg = rw_cfg.deep_copy()
    test_file_contents = client.get_text_file(file_name)

    with open(test_file_path, "r") as f:
        assert f.read() == test_file_contents

    assert rw_cfg["one"][0]["pink"] == "martini"
    assert rw_cfg["one"][0]["red"] == "apples"

    rw_cfg["one"][0]["red"] = "strawberry"
    rw_cfg["one"][0]["pink"] = "raspberry"

    try:
        rw_cfg.save()

        beacon.reload()

        rw_cfg2 = beacon.get_config(node_name)

        assert id(rw_cfg2) != id(rw_cfg)
        assert rw_cfg2["one"][0]["red"] == "strawberry"
        assert rw_cfg2["one"][0]["pink"] == "raspberry"
    finally:
        with open(test_file_path, "w") as f:
            f.write(test_file_contents)


def test_empty_yml(beacon, beacon_directory):
    new_file = "%s/toto.yml" % beacon_directory

    try:
        with open(new_file, "w") as f:
            f.write(" ")

        assert pytest.raises(RuntimeError, beacon.reload)

        with pytest.raises(RuntimeError) as e_info:
            beacon.reload()
        assert "filename" in str(e_info.value)
    finally:
        os.unlink(new_file)


def test_yml_load_error(beacon, beacon_directory):
    new_file = "%s/change_size_error.yml" % beacon_directory

    try:
        with open(new_file, "w") as f:
            f.write(
                """- name: change_size_error
  a:
    b:
      - c """
            )

        beacon.reload()
        change_size_error = beacon.get("change_size_error")
    finally:
        os.unlink(new_file)


@pytest.mark.parametrize(
    "object_name, get_func_name, copy, ref_func",
    [
        ["refs_test", "get", False, None],
        ["refs_test_cpy", "get_config", True, replace_reference_by_object],
    ],
)
def test_references(beacon, object_name, get_func_name, copy, ref_func):
    get_func = getattr(beacon, get_func_name)
    refs_cfg = get_func(object_name)
    if copy:
        refs_cfg = refs_cfg.deep_copy()
    if ref_func:
        ref_func(beacon, refs_cfg)

    m0 = beacon.get("m0")
    s1hg = beacon.get("s1hg")
    s1vo = beacon.get("s1vo")

    try:
        assert repr(refs_cfg["scan"]["axis"]) == repr(m0)
        assert repr(refs_cfg["slits"][0]["axis"]) == repr(s1hg)
        assert refs_cfg["slits"][0]["position"] == 0
        assert repr(refs_cfg["slits"][1]["axis"]) == repr(s1vo)
        assert refs_cfg["slits"][1]["position"] == 1
        assert repr(refs_cfg["m0"]) == repr(m0)
    finally:
        m0.__close__()
        s1hg.__close__()
        s1vo.__close__()


def test_issue_451_infinite_recursion(beacon):
    refs_cfg = beacon.get_config("refs_test")

    refs_cfg.get_inherited(
        "toto"
    )  # key which does not exist, was causing infinite recursion

    assert refs_cfg.parent == beacon.root
    assert refs_cfg in beacon.root["__children__"]

    assert beacon.root.parent is None


class DummyObject:
    def __init__(self, name, config):
        assert config.get("t_value")


def test_inherited_package(beacon):
    try:
        sys.path.append(os.path.dirname(__file__))
        assert isinstance(beacon.get("dummy1"), DummyObject)
        assert isinstance(beacon.get("dummy2"), DummyObject)
    finally:
        sys.path.pop()


def test_yaml_boolean(beacon):
    m = beacon.get("fake_multiplexer_config")

    assert m["outputs"][0]["ON"] == 1
    assert m["outputs"][0]["OFF"] == 0


def test_config_save_reference(beacon, beacon_directory):
    file_name = "read_write_2.yml"
    node_name = "rw_test_2"
    rw_cfg = beacon.get_config(node_name).deep_copy()
    replace_reference_by_object(beacon, rw_cfg, dict())
    diode = beacon.get("diode")
    diode2 = beacon.get("diode2")
    diode3 = beacon.get("diode3")

    rw_cfg["test_list"].append(diode2)
    rw_cfg["dict_list"].append({"cnt_channel": "c", "instance": diode})
    rw_cfg.save()

    beacon.reload()

    rw_cfg2 = beacon.get_config(node_name)
    replace_reference_by_object(beacon, rw_cfg2, dict())
    assert id(rw_cfg2) != id(rw_cfg)
    assert len(rw_cfg2["test_list"]) == len(rw_cfg["test_list"])
    assert [x.name for x in rw_cfg2["test_list"]] == [
        x.name for x in rw_cfg["test_list"]
    ]
    assert len(rw_cfg2["dict_list"]) == len(rw_cfg["dict_list"])
    assert (
        rw_cfg2["dict_list"][2]["instance"].name
        == rw_cfg["dict_list"][2]["instance"].name
    )


def test_bad_icepap_host(beacon):
    bad_mot = beacon.get("v6biturbo")

    with pytest.raises(RuntimeError):
        a = bad_mot.position
