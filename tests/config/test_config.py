# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.conductor import client
import pytest
import os


def test_config_save(beacon, beacon_directory):
    test_file_path = os.path.join(beacon_directory, "read_write.yml")
    rw_cfg = beacon.get_config("rw_test")
    test_file_contents = client.get_config_file("read_write.yml")

    with open(test_file_path, "r") as f:
        assert f.read() == test_file_contents

    assert rw_cfg["one"][0]["pink"] == "martini"
    assert rw_cfg["one"][0]["red"] == "apples"

    rw_cfg["one"][0]["red"] = "strawberry"
    rw_cfg["one"][0]["pink"] = "raspberry"

    try:
        rw_cfg.save()

        beacon.reload()

        rw_cfg2 = beacon.get_config("rw_test")

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


def test_references(beacon):
    refs_cfg = beacon.get("refs_test")
    m0 = beacon.get("m0")
    s1hg = beacon.get("s1hg")
    s1vo = beacon.get("s1vo")

    assert refs_cfg["scan"]["axis"].__repr__() == repr(m0)
    assert refs_cfg["slits"][0]["axis"].__repr__() == repr(s1hg)
    assert refs_cfg["slits"][0]["position"] == 0
    assert refs_cfg["slits"][1]["axis"].__repr__() == repr(s1vo)
    assert refs_cfg["slits"][1]["position"] == 1
    assert refs_cfg["m0"].__repr__() == repr(m0)

    # Clean-up
    m0.close()
    s1hg.close()
    s1vo.close()


def test_issue_451_infinite_recursion(beacon):
    refs_cfg = beacon.get_config("refs_test")

    refs_cfg.get_inherited(
        "toto"
    )  # key which does not exist, was causing infinite recursion

    assert refs_cfg.parent == beacon.root

    assert beacon.root.parent is None
