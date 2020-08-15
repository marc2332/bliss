# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.conductor import client
import pytest
import sys, os
import ruamel


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
        rw_cfg = rw_cfg.clone()
    test_file_contents = client.get_text_file(file_name)

    with open(test_file_path, "rb") as f:
        assert f.read().decode() == test_file_contents

    assert rw_cfg["one"][0]["pink"] == "martini"
    assert rw_cfg["one"][0]["red"] == "apples"

    for comment in ("comment{}".format(i) for i in range(1, 6)):
        assert comment in test_file_contents

    rw_cfg["one"][0]["red"] = "strawberry"
    rw_cfg["one"][0]["pink"] = "raspberry"

    try:
        rw_cfg.save()
        beacon.reload()
        with open(test_file_path) as f:
            content = f.read()
            for comment in ("comment{}".format(i) for i in range(1, 6)):
                assert comment in content

        rw_cfg2 = beacon.get_config(node_name)

        assert id(rw_cfg2) != id(rw_cfg)
        assert rw_cfg2["one"][0]["red"] == "strawberry"
        assert rw_cfg2["one"][0]["pink"] == "raspberry"
    finally:
        with open(test_file_path, "w") as f:
            f.write(test_file_contents)


def test_yml_load_exception(beacon, beacon_directory):
    new_file = "%s/bad.yml" % beacon_directory

    try:
        with open(new_file, "w") as f:
            f.write(
                """- name: bad_yml
    let:
    - 1
    - 2
"""
            )

        assert pytest.raises(ruamel.yaml.scanner.ScannerError, beacon.reload)
    finally:
        os.unlink(new_file)


def test_empty_yml(beacon, beacon_directory):
    new_file = "%s/toto.yml" % beacon_directory

    try:
        with open(new_file, "w") as f:
            f.write(" ")

        assert pytest.raises(RuntimeError, beacon.reload)

        with pytest.raises(RuntimeError) as exc:
            beacon.reload()
        assert "toto.yml" in str(exc.value)
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


def test_yml_load_error2(beacon, beacon_directory):
    new_file = "%s/change_size_error.yml" % beacon_directory

    try:
        with open(new_file, "w") as f:
            f.write(
                """- name: change_size_error
  a:
    b:
      c:
        d:
        - e """
            )

        beacon.reload()
        change_size_error = beacon.get("change_size_error")
    finally:
        os.unlink(new_file)


@pytest.mark.parametrize(
    "object_name, get_func_name, copy",
    [["refs_test", "get", False], ["refs_test_cpy", "get_config", True]],
)
def test_references(beacon, object_name, get_func_name, copy):
    get_func = getattr(beacon, get_func_name)
    refs_cfg = get_func(object_name)
    if copy:
        refs_cfg = refs_cfg.clone()

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
    rw_cfg = beacon.get_config(node_name).clone()
    diode = beacon.get("diode")
    diode2 = beacon.get("diode2")
    diode3 = beacon.get("diode3")

    rw_cfg["test_list"].append(diode2)
    rw_cfg["dict_list"].append({"cnt_channel": "c", "instance": diode})
    rw_cfg.save()

    beacon.reload()

    rw_cfg2 = beacon.get_config(node_name)
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


def test_capital_letter_file(beacon):
    # files starting with capital letter were causing problems,
    # see merge request !1524
    # (this was because the files were read before __init__.yml)
    # This test just makes sure the object from 'A.yml' is properly
    # returned as expected
    x = beacon.get("Aunused")
    assert x


def test_bliss_import_error(beacon):
    with pytest.raises(RuntimeError) as excinfo:
        beacon.get("broken_ctrl3")

    # Non existing class
    with pytest.raises(ModuleNotFoundError) as excinfo:
        beacon.get("broken_ctrl")
    assert "CONFIG COULD NOT FIND CLASS" in str(excinfo.value)

    # faulty import in imported module
    with pytest.raises(ModuleNotFoundError) as excinfo:
        beacon.get("broken_ctrl2")
    assert "CONFIG COULD NOT FIND CLASS" not in str(excinfo.value)


def test_config_eval(beacon):
    obj_cfg = beacon.get_config("test_config_eval")

    # ensure the reference is properly evaluated
    roby = beacon.get("roby")
    assert obj_cfg["mapping"]["mot"] == roby.position == 0
    assert obj_cfg["mapping"]["names"] == ["roby", "robz"]

    roby.position = 1

    # ensure reference is re-evaluated each time
    assert obj_cfg["mapping"]["mot"] == roby.position == 1


def test_references_list_inside_subdict(beacon):
    node = beacon.get_config("config_test")
    motor_list = node["mydict"]["mysubdict"]["motors"]
    assert motor_list == [beacon.get("roby"), beacon.get("robz")]


def test_issue_1619(beacon):
    obj_cfg = beacon.get_config("config_test")

    x = obj_cfg.get("test")

    obj = beacon.get("config_test")

    # by definition of the default plugin, the default plugin returns the
    # config node as the object so let's ensure both 'get_config' and 'get'
    # return the same thing
    assert obj_cfg is obj
    assert obj["test"] == x == obj_cfg["test"]


def test_user_tags(beacon):
    objs = [("diode", "diode2", "diode3"), ("robz",)]
    assert beacon.user_tags_list == ["TEST.DIODE", "TEST.ROBZ"]
    for obj_list, tag in zip(objs, beacon.user_tags_list):
        assert set(
            [beacon.get_config(obj) for obj in obj_list]
        ) == beacon.get_user_tag_configs(tag)
