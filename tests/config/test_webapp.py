# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import pytest
import requests
import os
import ast
import glob
import itertools
import shutil


def test_home(beacon, config_app_port, homepage_app_port):
    r = requests.get("http://localhost:%d" % config_app_port)
    assert r.status_code == 200  # OK

    r = requests.get("http://localhost:%d" % homepage_app_port)
    assert r.status_code == 200  # OK


def test_tree_files(beacon, config_app_port):
    r = requests.get("http://localhost:%d/tree/files" % config_app_port)
    assert r.status_code == 200  # OK


def test_db_files(beacon, config_app_port):
    r = requests.get("http://localhost:%d/db_files" % config_app_port)
    assert r.status_code == 200

    cfg_test_files_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "test_configuration")
    )
    db_files = set(
        itertools.chain(
            *[
                glob.glob(os.path.join(dp, "*.yml"))
                for dp, dn, fn in os.walk(cfg_test_files_path)
            ]
        )
    )
    assert (
        set([os.path.join(cfg_test_files_path, f) for f in ast.literal_eval(r.text)])
        == db_files
    )


def test_duplicated_key_on_new_file(beacon, beacon_directory, config_app_port):
    # copy the diode.yml to a new file
    diode_path = os.path.join(beacon_directory, "diode.yml")
    diode1_path = os.path.join(beacon_directory, "diode1.yml")

    shutil.copyfile(diode_path, diode1_path)
    r = requests.get("http://localhost:%d/config/reload" % config_app_port)
    os.remove(diode1_path)

    assert r.status_code == 200  # OK


def test_duplicated_key_on_same_file(beacon, beacon_directory, config_app_port):
    file_content = """\
-
  name: diode_test
  plugin: bliss
  class: simulation_diode
  independent: True
"""
    filename = "diode_duplicated_key.yml"
    filepath = os.path.join(beacon_directory, filename)
    with open(filepath, "w") as f:
        f.write(file_content)

    with open(filepath, "w") as f:
        f.write(file_content)
        f.write(file_content)  # write twice to raise key error

    r = requests.get("http://localhost:%d/config/reload" % config_app_port)
    os.remove(filepath)

    assert r.status_code == 200  # OK
