# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import pytest
import requests
import os
import ast
import glob
import itertools


def test_home(beacon, config_app_port):
    r = requests.get("http://localhost:%d" % config_app_port)
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
